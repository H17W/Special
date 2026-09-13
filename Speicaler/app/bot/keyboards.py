from aiogram.types import InlineKeyboardMarkup,InlineKeyboardButton

def kb(rows): return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=t,callback_data=d) for t,d in r] for r in rows])
def main_menu(owner=False):
 rows=[[('👤 إدارة الحساب','account'),('📥 إدارة الخاص','private')],[('📦 التخزين والحفظ','storage'),('🛡️ الحماية والإدارة','security')],[('🤖 الأدوات الذكية','tools'),('📢 الإذاعة','broadcast')],[('📊 الإحصائيات','stats'),('📖 دليل Special','help')]]
 if owner: rows.append([('🛡️ لوحة المطور','admin')])
 return kb(rows)
def back(data='back'): return kb([[('↩️ رجوع',data),('🏠 الرئيسية','home')]])
def admin_menu(): return kb([[('👥 المستخدمون','adm_users'),('📨 طلبات الوصول','admin_requests')],[('⏱️ الوصول المؤقت','admin_link'),('🚫 تقييد المستخدمين','admin_restrict')],[('📢 الإذاعة','broadcast'),('📜 سجل العمليات','audit')],[('🧹 تنظيف البوت','cleanup'),('📊 إحصائيات النظام','stats')],[('🩺 صحة النظام','health'),('💾 النسخ الاحتياطي','backup')],[('⚙️ إعدادات Special','settings')],[('↩️ رجوع','home')]])
def request_actions(rid): return kb([[('✅ قبول دائم',f'req:accept:{rid}:0'),('🕐 قبول 24 ساعة',f'req:accept:{rid}:86400')],[('📅 قبول 7 أيام',f'req:accept:{rid}:604800')],[('❌ رفض',f'req:reject:{rid}:none'),('✏️ رفض مع سبب',f'req:reject:{rid}:reason')]])
def cleanup_menu(): return kb([[('📜 سجل العمليات','clean:operations'),('📥 سجل الخاص','clean:private_log')],[('📨 طلبات الوصول','clean:access'),('📢 الإذاعات','clean:broadcast')],[('💾 التخزين','clean:storage')],[('🧹 تنظيف الكل','clean:all')],[('↩️ رجوع','admin')]])
def audio_actions(): return kb([[('🎙️ تحويل إلى فويس','audio:convert'),('📝 تعديل الاسم والفنان','audio:edit')],[('↩️ رجوع','home')]])
