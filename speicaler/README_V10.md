# Special V10

نسخة محدثة من Special مبنية على V9 مع الحفاظ على الخصائص السابقة.

## أهم إصلاحات V10
- ADMIN_ID يدعم `ADMIN_ID` أو `OWNER_ID`.
- تشغيل Bot polling مستقل عن فشل جلسة Telethon.
- حذف أي webhook قبل بدء polling.
- التحقق من البوت وطباعة username وID عند التشغيل.
- تسجيل واضح عند وصول `/start`.
- إعادة محاولة تلقائية عند خطأ `database is locked` في جلسة Telethon.

## التشغيل
```bash
pip install -r app/requirements.txt
python -m app.main
```
