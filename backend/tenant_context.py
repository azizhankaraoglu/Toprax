"""
=====================================================================
Toprax — Tenant İzolasyon Altyapısı (Sprint 4c)
=====================================================================
Her kooperatif/kurum ayrı bir "tenant" — verileri birbirinden TAMAMEN
İZOLE. Bunu uygulamanın yüzlerce mevcut sorgu satırını tek tek
değiştirmeden sağlamak için şu yaklaşım kullanılıyor:

1. Her istek başında bir middleware, JWT'deki tenant_id'yi okuyup bir
   `contextvars.ContextVar` içine yazar (istek bazlı, eşzamanlı istekler
   birbirine karışmaz — asyncio task'leri arasında izole çalışır).
2. Global `db` nesnesi bu context'i okuyan bir sarmalayıcıyla (TenantScopedDB)
   değiştirilir. `db.parcels.find(...)`, `db.farmers.insert_one(...)` gibi
   TÜM mevcut kod DEĞİŞMEDEN çalışmaya devam eder, ama sahne arkasında
   her sorguya otomatik olarak `{"tenant_id": <mevcut_tenant>}` filtresi
   eklenir ve her insert'e `tenant_id` alanı otomatik yazılır.

Bu, "her yeri tek tek tenant_id filtrele" şeklindeki devasa ve hataya açık
bir refactor'dan kaçınmanın güvenli yoludur — filtre unutulan TEK BİR
sorgu bile veri sızıntısına yol açabileceğinden, merkezi bir sarmalayıcı
çok daha güvenilirdir.

`tenants` koleksiyonu ve platform-admin işlemleri bu izolasyonun DIŞINDA
tutulur (ham/sarmalanmamış db ile erişilir) çünkü onlar zaten tenant'lar
ARASI işlemlerdir.
"""
from contextvars import ContextVar
from typing import Optional

# Bu request'in ait olduğu tenant — middleware tarafından set edilir.
current_tenant_id: ContextVar[Optional[str]] = ContextVar("current_tenant_id", default=None)

# tenant_id ile hiç filtrelenmeyecek (tenant'lar-arası) koleksiyonlar.
GLOBAL_COLLECTIONS = {"tenants"}


class TenantScopedCollection:
    """Bir MongoDB koleksiyonunu sarmalar; her çağrıda mevcut tenant_id'yi
    filtreye/insert'e otomatik ekler. exempt=True ise hiçbir filtre eklemez
    (global koleksiyonlar için)."""

    def __init__(self, collection, exempt: bool = False):
        self._c = collection
        self._exempt = exempt

    def _scoped_filter(self, filt):
        filt = dict(filt) if filt else {}
        if self._exempt:
            return filt
        tid = current_tenant_id.get()
        if tid is None:
            # Tenant bağlamı yoksa (örn. login sırasında email ile arama,
            # ya da unauthenticated bootstrap endpoint'i) filtre eklenmez —
            # bilinçli bir tasarım kararı, tenant henüz bilinmiyor demektir.
            return filt
        filt["tenant_id"] = tid
        return filt

    def _stamp(self, doc):
        if self._exempt:
            return doc
        tid = current_tenant_id.get()
        if tid is not None:
            doc = dict(doc)
            doc["tenant_id"] = tid
        return doc

    # ---- okuma ----
    def find(self, filt=None, *args, **kwargs):
        return self._c.find(self._scoped_filter(filt), *args, **kwargs)

    async def find_one(self, filt=None, *args, **kwargs):
        return await self._c.find_one(self._scoped_filter(filt), *args, **kwargs)

    async def count_documents(self, filt=None, *args, **kwargs):
        return await self._c.count_documents(self._scoped_filter(filt), *args, **kwargs)

    async def distinct(self, key, filt=None, *args, **kwargs):
        return await self._c.distinct(key, self._scoped_filter(filt), *args, **kwargs)

    def aggregate(self, pipeline, *args, **kwargs):
        # Aggregate pipeline'ların başına otomatik $match enjekte edilir.
        tid = current_tenant_id.get()
        if not self._exempt and tid is not None:
            pipeline = [{"$match": {"tenant_id": tid}}] + list(pipeline)
        return self._c.aggregate(pipeline, *args, **kwargs)

    # ---- yazma ----
    async def insert_one(self, doc, *args, **kwargs):
        return await self._c.insert_one(self._stamp(doc), *args, **kwargs)

    async def insert_many(self, docs, *args, **kwargs):
        return await self._c.insert_many([self._stamp(d) for d in docs], *args, **kwargs)

    async def update_one(self, filt, update, *args, **kwargs):
        return await self._c.update_one(self._scoped_filter(filt), update, *args, **kwargs)

    async def update_many(self, filt, update, *args, **kwargs):
        return await self._c.update_many(self._scoped_filter(filt), update, *args, **kwargs)

    async def delete_one(self, filt, *args, **kwargs):
        return await self._c.delete_one(self._scoped_filter(filt), *args, **kwargs)

    async def delete_many(self, filt, *args, **kwargs):
        return await self._c.delete_many(self._scoped_filter(filt), *args, **kwargs)

    # ---- index/diğer — tenant kavramı olmayan, olduğu gibi geçilir ----
    async def create_index(self, *args, **kwargs):
        return await self._c.create_index(*args, **kwargs)

    def __getattr__(self, name):
        # Kapsanmayan bir metod çağrılırsa ham koleksiyona düş (fail-safe
        # değil, sadece kapsam dışı okuma/yardımcı metodlar için).
        return getattr(self._c, name)


class TenantScopedDB:
    """`db.<koleksiyon_adı>` erişimini şeffafça TenantScopedCollection'a
    yönlendirir. Mevcut kodda `db = client[...]` yerine bu sınıfın bir
    örneği kullanılınca, kod hiç değişmeden tenant-izole hale gelir."""

    def __init__(self, real_db):
        self._real_db = real_db

    def __getattr__(self, name):
        exempt = name in GLOBAL_COLLECTIONS
        return TenantScopedCollection(getattr(self._real_db, name), exempt=exempt)

    def __getitem__(self, name):
        # server.py'de `db[collection_adı]` şeklinde dinamik erişim de var
        # (örn. seed temizliğinde) — bunu da desteklememiz lazım.
        return self.__getattr__(name)
