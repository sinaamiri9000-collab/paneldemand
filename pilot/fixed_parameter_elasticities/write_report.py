"""Render fixed-parameter post-estimation results; never estimate a model."""
if __package__ in (None, ''):
    import sys
    from pathlib import Path as _Path
    sys.path.insert(0,str(_Path(__file__).resolve().parents[2]))
import json
from pathlib import Path
import numpy as np

OUT=Path(__file__).parent

def main():
    data=json.loads((OUT/'results.json').read_text());groups=data['groups'];lines=[]
    def add(s=''):lines.append(s)
    def table(headers,rows):
        add('| '+' | '.join(map(str,headers))+' |');add('| '+' | '.join(['---']*len(headers))+' |')
        for row in rows:add('| '+' | '.join(map(str,row))+' |')
        add()
    def fmt(x):return f'{x:.4f}'
    def vector(r,metric,micro=False):
        if micro:
            a=np.array(r['micro']['individual_expenditure' if metric=='expenditure' else 'individual_marshallian']['median'])
        else:a=np.array(r['elasticities'][metric])
        return a if metric=='expenditure' else np.diag(a)
    add('# کشش‌ها با ضرایب ثابت در میانگین کل نمونه، سال و cohort')
    add('\nتاریخ: ۲۰۲۶–۱۰–۱۰. این بسته فقط محاسبهٔ پس از تخمین برای **B1_no_season_means و B2_no_season_means** است. هیچ ضریب تقاضا، مشارکت یا مرحلهٔ اول دوباره تخمین زده نشده است. تمام نتایج قبلی حفظ شده‌اند.\n')
    add('## نتیجهٔ اصلی\n')
    add('حتی با ضرایب مشترک، کشش‌ها به نقطهٔ ارزیابی بستگی دارند. برای هر مدل ۲۱ نقطه محاسبه شد: کل ۱۳۷٬۸۱۴ مشاهدهٔ ۴۵٬۹۳۸ خانوار، ۱۲ سال ۱۳۹۲–۱۴۰۳ و ۸ cohort ورود. تفاوت‌های زیر حاصل تفاوت شرایط مشاهده‌شده و کنترل‌های مدل‌اند؛ آزمون تغییر ضرایب یا شاهد علی تغییر ترجیحات نیستند.\n')
    rows=[]
    for i,g in enumerate(groups):
        row=[g]
        for model in data['models'].values():
            row += [fmt(vector(model['global'],'expenditure')[i]),fmt(vector(model['global'],'marshallian')[i]),
                    fmt(model['ranges']['years']['expenditure']['range'][i]),fmt(model['ranges']['years']['marshallian']['range'][i]),
                    fmt(model['ranges']['cohorts']['expenditure']['range'][i]),fmt(model['ranges']['cohorts']['marshallian']['range'][i])]
        rows.append(row)
    table(['گروه','B1 مخارج کل','B1 خودقیمتی کل','B1 دامنه سال مخارج','B1 دامنه سال خودی','B1 دامنه cohort مخارج','B1 دامنه cohort خودی',
           'B2 مخارج کل','B2 خودقیمتی کل','B2 دامنه سال مخارج','B2 دامنه سال خودی','B2 دامنه cohort مخارج','B2 دامنه cohort خودی'],rows)
    add('دامنه = بیشینه منهای کمینه؛ اندازهٔ اختلاف کشش است و مقدار احتمال یا فاصلهٔ اطمینان نیست. مقایسهٔ اقتصادی باید با توجه به سطح کشش، نوع کالا و حساسیت نقطهٔ ارزیابی انجام شود. برای تفسیر دقیق، سال‌های کمینه/بیشینه و میانهٔ مشاهده‌ای نیز پایین آمده‌اند.\n')
    add('برنج از نظر اقتصادی نسبتاً ثابت است: کشش خودقیمتی سالانهٔ B1 از −۱٫۰۸۲۲ تا −۱٫۰۷۳۷ و B2 از −۱٫۰۸۰۹ تا −۱٫۰۷۰۵ تغییر می‌کند. در مقابل، کشش خودقیمتی روغن در B1 از −۰٫۶۱۰۲ تا −۰٫۳۸۵۰ و در B2 از −۰٫۶۱۵۷ تا −۰٫۳۷۹۲ است؛ اختلاف حدود ۰٫۲۳ را نباید مانند اختلاف حدود ۰٫۰۱ برنج تفسیر کرد.\n')
    add('برای روغن، کشش مخارج سالانهٔ B1 بین ۰٫۶۴۹۳ و ۰٫۹۰۸۵ است، ولی B2 بین ۱٫۰۰۳۴ و ۱٫۱۰۷۴ قرار دارد. برای مغزها/خشکبار/خرما این بازه‌ها به‌ترتیب ۲٫۰۳۸۶–۲٫۳۲۴۹ و ۱٫۵۲۵۵–۱٫۷۶۰۷ هستند. بنابراین تفاوت اصلی دو تصریح در این گروه‌ها فقط محصول انتخاب میانگین کل نمونه نیست و در نقاط سالانه هم باقی می‌ماند. نزدیک‌بودن کران روغن B2 به یک به معنی اثبات آماری لوکس‌بودن آن نیست.\n')
    add('نان و غلات نیاز به توجه جداگانه دارد: کشش مخارج در نقطهٔ میانگین سال ۱۴۰۳ در B1 برابر −۰٫۲۱۶۴ و در B2 برابر −۰٫۴۳۶۱ است، درحالی‌که در ۱۳۹۲ به‌ترتیب ۰٫۵۷۲۲ و ۰٫۴۷۵۷ بوده است. سهم مرجع همچنان مثبت است و مشتق عددی کنترل شده؛ بنابراین این علامت منفی صرفاً خطای تقسیم بر سهم نامثبت نیست. این نتیجهٔ شرطی مدل است، نه اثبات اینکه افزایش درآمد حتماً مصرف نان را کاهش می‌دهد. میانهٔ کشش مشاهده‌ای در ۱۴۰۳ هم منفی است: −۰٫۱۱۰۲ در B1 و −۰٫۳۳۰۴ در B2؛ بنابراین علامت منفی فقط وابسته به انتخاب نقطهٔ میانگین نیست.\n')
    add('## فرایند و تعریف کشش\n')
    add('برای زیرگروه g، ورودی مرجع میانگین حسابیِ **لگاریتم** قیمت و مخارج و میانگین کنترل‌های همان مشاهدات است؛ قیمت و مخارج مرجع در مقیاس اصلی بنابراین میانگین هندسی‌اند. وزن survey در این میانگین‌ها به کار نرفته، مطابق محاسبهٔ مستقیم قبلی. میانگین‌های موندلاک خانوار همچنان از سه موج اصلی ساخته شده‌اند؛ با برش سالانه مجدداً محاسبه نشده‌اند. مقیاس‌ها، مرکزسازی، a0، CF و ضرایب Probit متعلق به برازش اصلی‌اند. احتمال خرید در نقطهٔ میانگین برابر Phi(mean index) است، نه mean Phi(index).\n')
    add('مدل سهم برازش‌شده به‌صورت زیر است؛ تمام ضرایب در تمام نقاط ثابت‌اند:\n')
    add(r'$$\mu_i=\Phi(k_i)\,[g_i(\log p,\log x,Z;\hat\theta)+\kappa_i\hat v+\omega_i\overline{\hat v}]+\delta_i\phi(k_i).$$'+'\n')
    add('g تابع QUAIDS با ترجمهٔ alpha و کنترل‌های مدل است؛ B2 میانگین لگاریتم مخارج را نیز در این ترجمه دارد. k شاخص Probit برازش‌شده است. کنترل‌های موندلاک، CF جاری و میانگین CF هنگام مشتق جاری ثابت‌اند؛ ولی اثر قیمت/مخارج جاری بر شاخص مشارکت و در نتیجه بر Phi و phi در مشتق حفظ می‌شود.\n')
    add(r'$$\epsilon^x_i=1+\frac{\partial\mu_i/\partial\log x}{\mu_i},\qquad \epsilon^M_{ij}=\frac{\partial\mu_i/\partial\log p_j}{\mu_i}-\mathbf1(i=j).$$'+'\n')
    add('کشش نقطهٔ میانگین برابر میانگین یا میانهٔ کشش‌های خانوارها نیست. برای بررسی حساسیت، میانهٔ کشش‌های تک‌مشاهده‌ای هر سال/cohort نیز مستقل محاسبه شده است. JSON همچنین میانگین، انحراف معیار، صدک‌ها، تعداد معتبر، کشش‌های نهفته و خلاصهٔ مقدار کل برازش‌شده را نگه می‌دارد. مقدار کل بر پایهٔ sum exp(log x-log p_i)*mu_i است و واحد فیزیکی کیلوگرم ندارد.\n')
    add('این مدل‌ها در مشارکت، **Probit تجمیعی با کنترل‌های موندلاک** دارند؛ مدل کامل RE-Probit با انتگرال‌گیری نیستند. وجود دامی‌های جاری سال، فصل و cohort و حذف میانگین فصل دقیقاً مطابق برازش قبلی حفظ شده؛ wave و تحصیلات وجود ندارند. دامی‌های سال در برش سالانه ثابت‌اند، اما میانگین دامی cohort بر اساس ترکیب همان سال ساخته می‌شود؛ برای cohort نیز عکس آن برقرار است. تغییر سال/cohort در این گزارش شامل تفاوت ترکیب نمونه، کنترل‌های سطحی و احتمال خرید هم هست.\n')
    add('در مدل S&Y خام، مجموع سهم‌های برازش‌شده الزاماً یک نیست. ماتریس «هیکسین» زیر فقط قرارداد تشخیصی Slutsky یعنی epsilonM+epsilonX*mu است؛ معادل یک سیستم جبران‌شدهٔ دقیق و تضمین‌شده نیست. قیود بخش نهفته حفظ شده‌اند و قید انحنای تازه‌ای اعمال نشده است.\n')
    add('## اندازهٔ نمونه\n')
    first=next(iter(data['models'].values()))
    for kind,label in [('years','سال مشاهده'),('cohorts','سال ورود cohort')]:
        table([label,'مشاهدات','خانوارهای متمایز'],[[key,r['observations'],r['households']] for key,r in first[kind].items()])
    add('هر تفکیک کل ۱۳۷٬۸۱۴ مشاهده را پوشش می‌دهد. cohort از سال ورود ثبت‌شده گرفته شده و هر خانوار با هر سه مشاهده در همان cohort قرار دارد؛ دورهٔ سه‌سالهٔ دلخواه جدیدی ساخته نشده است. خانوارهای سال‌های مختلف همپوشانی دارند.\n')
    for name,model in data['models'].items():
        add('## '+name+'\n')
        add('### کمینه و بیشینهٔ کشش در نقاط میانگین\n')
        for kind,label in [('years','سال‌ها'),('cohorts','cohortها')]:
            add('**'+label+'**\n')
            rows=[]
            for i,g in enumerate(groups):
                row=[g]
                for metric in ['expenditure','marshallian']:
                    q=model['ranges'][kind][metric];row += [fmt(q['minimum'][i]),q['minimum_at'][i],fmt(q['maximum'][i]),q['maximum_at'][i]]
                rows.append(row)
            table(['گروه','کمینه مخارج','در','بیشینه مخارج','در','کمینه خودقیمتی','در','بیشینه خودقیمتی','در'],rows)
        for kind,label in [('years','سال'),('cohorts','cohort')]:
            for micro,title in [(False,'کشش در نقطهٔ میانگین'),(True,'میانهٔ کشش‌های مشاهده‌ای')]:
                for metric,title2 in [('expenditure','مخارج'),('marshallian','خودقیمتی مارشالی')]:
                    add('### '+title+' — '+title2+' به تفکیک '+label+'\n')
                    records={'کل':model['global'],**model[kind]}
                    table([label]+groups,[[key]+[fmt(x) for x in vector(r,metric,micro)] for key,r in records.items()])
        add('### کنترل صحت و پشتیبانی محاسبات\n')
        records={'کل':model['global'],**{'سال '+k:r for k,r in model['years'].items()},**{'cohort '+k:r for k,r in model['cohorts'].items()}}
        table(['نقطه','مجموع سهم پیش‌بینی‌شده','کمترین سهم مرجع','بیشترین خطای مشتق'],[[key,fmt(r['reference_diagnostics']['predicted_share_sum']),fmt(min(r['reference_diagnostics']['predicted_shares'])),f"{r['derivative_validation']['max_absolute_error']:.2e}"] for key,r in records.items()])
        table(['گروه','سهم نامثبت در کل نمونه','کشش مخارج با قدرمطلق بالای ۱۰۰','تعداد کشش معتبر'],[[g,model['global']['micro']['nonpositive_fitted_share_count'][i],model['global']['micro']['individual_abs_expenditure_over_100_count'][i],model['global']['micro']['individual_expenditure']['valid_count'][i]] for i,g in enumerate(groups)])
        add('این مشاهدات از نمونهٔ تخمین حذف نشده‌اند. کشش لگاریتمی مشاهده‌ای فقط برای سهم برازش‌شدهٔ مثبت تعریف شده؛ تعداد معتبر و نامعتبر هر سال/cohort در JSON ثبت است. هیچ کشش پرت برش یا winsorize نشده است؛ میانگین مشاهده‌ای ممکن است به سهم‌های نزدیک صفر حساس باشد، به همین دلیل جدول میانه هم ارائه شده است.\n')
        add('### ماتریس‌های کامل در تمام نقاط مرجع\n')
        add('ردیف = گروه تقاضا، ستون = گروه قیمت؛ شماره‌ها ترتیب ۱۲ گروه جدول‌های بالا را دارند. هر ماتریس بدون تغییر ضرایب ارزیابی شده است. نسخهٔ با دقت کامل در JSON است.\n')
        for key,r in records.items():
            add('#### '+key+'\n')
            for metric,title in [('marshallian','مارشالی مستقیم'),('hicksian_slutsky_convention','Slutsky تشخیصی')]:
                add('**'+title+'**\n');table(['گروه']+list(range(1,13)),[[str(i+1)]+[fmt(x) for x in row] for i,row in enumerate(r['elasticities'][metric])])
    add('## بازتولید و محدودیت استنباط\n')
    add('ضرایب مشترک هر مدل در results.json یک بار ذخیره شده‌اند؛ برای شرح تمام ضرایب مرحلهٔ اول، مشارکت و تقاضا به [گزارش برازش اصلی](../specification_followup/report.md) مراجعه کنید. خطاهای استاندارد ضرایب داخل JSON از برازش قبلی کپی شده‌اند؛ برای نقاط مرجع تازه محاسبه نشده‌اند. فایل تازه تمام نقاط مرجع، ماتریس‌های کامل مارشالی، Slutsky تشخیصی و نهفته، توزیع مشاهده‌ای و پارامترهای تقاضا را دارد.\n')
    add('پارامترهای اصلی، tau و ماتریس کنترل‌ها پس از محاسبه با ورودی اولیه برابرند؛ SHA256 فایل‌های برازش در JSON است. ۴۵۶ خروجی کشش کل نمونه و میانه‌های مشاهده‌ای با محاسبهٔ پیشین تا خطای ۲e−۱۲ کنترل شدند. مشتق‌ها در هر ۴۲ نقطه مستقل با تفاضل مرکزی کنترل شدند؛ آستانهٔ خطا ۱e−۷ است.\n')
    add('این بسته فاصلهٔ اطمینان یا آزمون معناداری سال/cohort ندارد؛ تغییرات گزارش‌شده توصیفی‌اند. فاصله‌های اطمینان مقایسهٔ کل نمونه در بستهٔ قبلی به این مقایسه‌ها تعمیم داده نمی‌شوند. قیمت‌های ساخته‌شده و نمونهٔ نهایی ثابت‌اند؛ مرحلهٔ اول، مشارکت، IFGNLS و bootstrap دوباره اجرا نشده‌اند. این خروجی جای آزمون ثبات ضرایب را نمی‌گیرد، بلکه نشان می‌دهد پیش از آزادکردن ضرایب چه اختلافی با همان ضرایب ایجاد می‌شود.\n')
    add('```bash\npython -m pilot.fixed_parameter_elasticities.run --inputs intermediate/pilot_inputs\npython -m pilot.fixed_parameter_elasticities.write_report\n```\n')
    add('کد محاسبه: [run.py](run.py)، کد گزارش: [write_report.py](write_report.py)، نتایج: [results.json](results.json). داده و pickleهای خانوار در مخزن منتشر نمی‌شوند.\n')
    (OUT/'report.md').write_text('\n'.join(lines))

if __name__=='__main__':main()
