"""
=====================================================================
Toprax — Ortak Arama Yardımcıları (BULGU 2 düzeltmesi)
=====================================================================
Serbest metin arama kutusundan gelen `q` değeri MongoDB `$regex`'ine
KONULMADAN ÖNCE bu modülden geçirilir. `re.escape(...)` ile kaçışlanır
ve uzunluğu sınırlanır. Böylece:

  - Regex injection: kullanıcının `(`, `[`, `\` gibi özel karakterlerle
    beklenmedik eşleşme veya sorgu hatası üretmesi engellenir (girdi
    birebir/literal metin olarak aranır).
  - ReDoS / katastrofik geri-izleme: `(a+)+$` gibi bir "regex bombası"
    artık desen olarak yorumlanmaz; CPU'yu kilitleyemez.

TEST-PLANI T-08 gereği ("regex bombası, çok uzun string verilip sistemin
çökmediğini doğrula"). Hem server.py çiftçi araması hem crud_base.py
generic araması bu tek yardımcıyı kullanır.
"""
import re

# Serbest metin arama girdisi için üst sınır — bundan uzun girdiler
# hem gereksiz hem de DoS yüzeyini artırır.
MAX_SEARCH_LEN = 100

# BULGU 4 düzeltmesi: Türkçe locale collation. Arama ve sıralamada
# noktalı/noktasız İ-ı ve Ş/Ğ/Ç/Ö/Ü karakterlerinin doğru katlanması ve
# alfabetik sıralanması için MongoDB sorgularında kullanılır.
# strength=1 -> büyük/küçük harf ve aksan duyarsız eşleşme.
TR_COLLATION = {"locale": "tr", "strength": 1}


def safe_regex(q, max_len: int = MAX_SEARCH_LEN) -> str:
    """Kullanıcı girdisini güvenli, birebir (literal) aranabilir bir regex
    desenine çevirir: baştaki/sondaki boşlukları temizler, uzunluğu kırpar
    ve tüm regex meta-karakterlerini kaçışlar."""
    if not q:
        return ""
    return re.escape(str(q).strip()[:max_len])
