from configuration.models import JournalConfiguration

def can_user_access_pdf(user, paper):
    # 1. إذا كان المستخدم آدمن أو محرر في النظام، يملك صلاحية مطلقة دائماً
    if user.is_authenticated and (user.is_staff or user.is_superuser):
        return True
        
    # 2. إذا كان المستخدم هو نفسه الباحث الذي كتب الورقة، يحق له تحميلها دائماً
    if user.is_authenticated and user == paper.author:
        return True

    # 3. جلب النظام الحالي المفعل من قبل الآدمن
    config = JournalConfiguration.objects.first()
    current_mode = config.system_mode if config else 'full_open'

    # 4. تطبيق شروط الأنماط الأربعة:
    
    if current_mode == 'full_open':
        return True

    if current_mode == 'abstract_only':
        return False  # لأننا استثنينا الإدارة والكاتب في الأعلى، البقية يرون الـ Abstract فقط

    if current_mode == 'full_closed':
        # هنا يحق للمشتركين فقط القراءة (إذا كان لديك نظام اشتراكات)
        if user.is_authenticated and getattr(user, 'has_active_subscription', False):
            return True
        return False

    if current_mode == 'hybrid':
        # إذا كان البحث معلماً بأنه مدفوع ومفتوح للعامة، يفتح للجميع
        if paper.is_paid_open_access:
            return True
        # إذا لم يكن مدفوعاً، يعامل معاملة المغلق (يحتاج اشتراك)
        if user.is_authenticated and getattr(user, 'has_active_subscription', False):
            return True
        return False

    return False