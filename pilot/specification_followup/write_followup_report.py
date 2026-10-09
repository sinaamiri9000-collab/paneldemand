"""A single complete Persian report for the prespecified follow-up experiments."""
# Support both direct scripts and python -m from the repository root.
if __package__ in (None, ""):
    import sys
    from pathlib import Path as _Path
    sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))

import json
from pathlib import Path
import numpy as np
from pilot.specification_suite.specification_suite import GROUPS
from pilot.specification_followup.specification_followup import NEW, OLD, OUT


def main():
    r = json.loads((OUT/'results.json').read_text()); lines = []
    def put(s=''):
        s=str(s)
        if s.startswith('#') and lines and lines[-1]!='': lines.append('')
        lines.append(s)
        if s.startswith('#'): lines.append('')
    def fmt(x): return f'{x:.7g}' if isinstance(x,(float,np.floating)) else str(x)
    def table(headers,rows):
        put(); put('| '+' | '.join(headers)+' |'); put('| '+' | '.join(['---']*len(headers))+' |')
        for row in rows: put('| '+' | '.join(fmt(v) for v in row)+' |')
        put()
    def matrix(title,values,labels=None):
        put('### '+title); a = np.asarray(values)
        table(['ردیف']+[f'G{i+1}' for i in range(a.shape[1])],
              [[labels[i] if labels else f'G{i+1}']+list(row) for i,row in enumerate(a)])
    def ci(v,s): return f'{v:.4f} [{v-1.96*s:.4f}, {v+1.96*s:.4f}]'
    def direct(name): return r['models'][name]['direct_elasticities']
    def value(name,kind,new=False):
        a = direct(name)['point'][kind] if new else r['models'][name]['elasticities'][kind]
        return np.asarray(a)
    def summary_comparison(c):
        ex=np.asarray(c['difference_expenditure']); ow=np.diag(c['difference_marshallian'])
        ix=int(np.argmax(np.abs(ex))); ip=int(np.argmax(np.abs(ow)))
        return f"بیشترین تغییر مخارج برای {GROUPS[ix]} {ex[ix]:+.4f} و بیشترین تغییر خودی برای {GROUPS[ip]} {ow[ip]:+.4f} است؛ {sum(c['main24_ci95_outside_plus_minus_0_1'])} اختلاف از ۲۴ پاسخ اصلی، با CI۹۵٪ بیرون ±۰٫۱ قرار دارد."

    put('# اجراهای تکمیلی: Pooled همسان، حذف میانگین فصل و مشتق مستقیم S&Y — ۲۰۲۶–۱۰–۰۹')
    put(); put('## نتیجهٔ اجرایی')
    put('سه تخمین تازه روی همان نمونه و همان قیمت‌ها اجرا شده‌اند. برآوردهای B0، B1 و B2 قبلی برای محاسبهٔ مشتق مستقیم استفاده شده‌اند و هیچ‌یک دوباره تخمین زده نشده‌اند. نتایج پنج اجرای پیشین در [گزارش قبلی](../specification_suite/report.md) حفظ شده‌اند. ثبات شیب‌ها بین سال‌ها و cohortها در این مرحله بررسی نشده است.')
    table(['اجرای جدید','همگرایی','پارامتر تقاضا','SSE سهم','RMSE سهم','سهم پیش‌بینی‌شدهٔ منفی (%)'],
          [[n,r['models'][n]['convergence']['success'],r['models'][n]['parameters']['demand'],
            r['models'][n]['convergence']['share_sse'],r['models'][n]['fit']['share_rmse_overall'],
            100*r['models'][n]['fit']['negative_share_fraction_overall']] for n in NEW])
    for key in ['B0_minus_P0_matched','B2_minus_B1','B1_no_season_means_minus_B1','B2_no_season_means_minus_B2']:
        put(f"**{key}، مشتق مستقیم:** "+summary_comparison(r['comparisons_direct'][key])); put()
    put('معیار ±۰٫۱ یک مقیاس توصیفی برای خواندن اختلاف‌هاست؛ مرز اثبات‌شدهٔ اهمیت اقتصادی نیست. فاصلهٔ اطمینان اختلاف دو مدل با توجه به استفادهٔ هر دو از همان خانوارها محاسبه شده است.')
    put()
    season_max=max(np.abs(r['comparisons_direct'][key]['difference_expenditure']).max()
                   for key in ('B1_no_season_means_minus_B1','B2_no_season_means_minus_B2'))
    put(f'حذف میانگین‌های فصل برای ادامه قابل دفاع است: بیشترین تغییر کشش مخارج مستقیم در نقطهٔ متوسط {season_max:.6f} است، هر ۲۴ اختلاف اصلی هر دو مدل در معیار توصیفی ±۰٫۱ کوچک‌اند، و condition معادلات استنباط به‌وضوح کاهش یافته است. این گزاره دربارهٔ نقطهٔ متوسط است؛ میانگین سادهٔ کشش مشاهده‌ای در نزدیکی سهم صفر حساس‌تر است.')
    put()
    put('پیشنهاد کاری، نگهداری B1_no_season_means به‌عنوان پایهٔ موقت و B2_no_season_means به‌عنوان رقیب جدی است. B1 تصحیح جاری/پایدار CF را حفظ می‌کند؛ در B2 باید شناسایی میانگین مخارج درون‌زا نیز قابل دفاع باشد. تفاوت اقتصادی مخارج در B2 با مشتق مستقیم، میانهٔ کشش خانوارها و خلاصهٔ مقداری باقی می‌ماند و نمی‌توان آن را صرفاً به قرارداد قبلی کشش نسبت داد. این پیشنهاد، تصریح نهایی مقاله را قفل نمی‌کند.')
    put()
    put('### آیا تفاوت B1 و B2 با محاسبهٔ مستقیم باقی می‌ماند؟')
    table(['گروه','مخارج B1، روش قبلی','مخارج B2، روش قبلی','مخارج B1، مستقیم','مخارج B2، مستقیم','اختلاف مستقیم [CI95]','p اصلاح Holm'],
          [[g,value('B1','expenditure')[i],value('B2','expenditure')[i],
            value('B1','expenditure',True)[i],value('B2','expenditure',True)[i],
            ci(r['comparisons_direct']['B2_minus_B1']['difference_expenditure'][i],
               r['comparisons_direct']['B2_minus_B1']['standard_error_expenditure'][i]),
            r['comparisons_direct']['B2_minus_B1']['pvalue_main24_holm'][i]] for i,g in enumerate(GROUPS)])
    put('B2 پاسخ به مخارج جاری را مشروط به سطح معمول مخارج خانوار اندازه می‌گیرد. پس اختلاف B1/B2 هم تفاوت برازش و هم تفاوت مجموعهٔ کنترل‌های ثابت هنگام مشتق‌گیری را دربر دارد. بزرگی یا معناداری اختلاف به‌تنهایی ثابت نمی‌کند کدام تصریح درست‌تر است.')
    put()
    put('در مشتق مستقیم، اختلاف کشش مخارج روغن، حبوبات، مغزها و ادویه پس از Holm معنادار است. سه گروه اول حتی با CI۹۵٪ از معیار توصیفی ±۰٫۱ بیرون‌اند؛ برای ادویه اندازهٔ اختلاف حدود ۰٫۱۶ است، اما CI به این اندازهٔ حداقلی قطعیت نمی‌دهد. بیشترین اختلاف کشش خودی B1/B2 حدود ۰٫۰۳۴ است و هیچ اختلاف خودی پس از Holm معنادار نیست.')
    put('### روش محاسبه بر اندازهٔ کشش خودی چه اثری دارد؟')
    table(['گروه','خودی B1، روش قبلی','خودی B1، مستقیم','خودی B2، روش قبلی','خودی B2، مستقیم'],
          [[g,value('B1','marshallian')[i,i],value('B1','marshallian',True)[i,i],
            value('B2','marshallian')[i,i],value('B2','marshallian',True)[i,i]] for i,g in enumerate(GROUPS)])
    put('مثلاً کشش خودی حبوبات B1 در روش قبلی حدود −۰٫۴۷ و در مشتق مستقیم حدود −۰٫۶۹ است. بنابراین برای گزارش عدد نهایی کشش، قرارداد محاسبه اهمیت دارد؛ در عین حال ثبات نسبی پاسخ قیمت بین B1/B2 با روش مستقیم نیز دیده می‌شود.')

    put('## سه تصریح جدید دقیقاً چه هستند؟')
    table(['نام','تغییر دقیق'],[
        ['P0_matched','سن همان mean_head_age در B0؛ مرحلهٔ اول مخارج، ضرایب و CF عین B0؛ سایر میانگین‌ها فقط از مشارکت و تقاضا حذف می‌شوند.'],
        ['B1_no_season_means','B1 با حذف mean_season_2/3/4 از RF، مشارکت و تقاضا؛ دامی‌های فصل جاری باقی می‌مانند؛ CF و میانگین آن دوباره ساخته می‌شوند.'],
        ['B2_no_season_means','همان حذف فصل در B2؛ میانگین log مخارج و CF جاری/میانگین باقی می‌مانند.']])
    put('P0_matched مدل Pooled در **مشارکت و تقاضا با مرحلهٔ اول مشترک CRE** است. مدل کاملاً Pooled در هر سه مرحله نیست. این انتخاب، اختلاف نهایی با B0 را از تغییر سن و تغییر ساخت CF جدا می‌کند. mean_head_age نیز آگاهانه کنترل مشترک هر دو است؛ مقایسه حذف ۲۰ میانگین دیگر را می‌سنجد، نه حذف همهٔ اطلاعات خانوار.')
    table(['کنترل همسانی Pooled/B0','نتیجه'],r['matched_pooled_checks'].items())
    put('در دو مدل بدون میانگین فصل، حذف در همهٔ مراحل انجام شده تا CF از مرحلهٔ اول ناسازگار با مدل جدید نیاید. بنابراین تغییر آن‌ها حساسیت کل زنجیره به حذف میانگین فصل است، نه فقط حذف سه ستون از معادلهٔ نهایی.')
    put()
    put('فصل مصاحبه تنها در ۲۷ خانوار از ۴۵٬۹۳۸ خانوار تغییر کرده است. دامی فصل جاری و میانگین خانوارِ همان دامی برای بقیهٔ خانوارها برابرند. حذف میانگین‌های فصل تعداد پارامتر و وابستگی بین ستون‌ها را کاهش می‌دهد؛ دامی جاری تفاوت فصلی بین خانوارها را همچنان کنترل می‌کند. با ثبات تقریباً کامل فصل، ضریب باقی‌ماندهٔ فصل را نباید اثر خالص تغییر فصل درون یک خانوار تفسیر کرد.')
    table(['مدل','ستون مشارکت','رتبه','condition مقیاس‌شدهٔ طراحی','condition مقیاس‌شدهٔ bread'],
          [[n,r['models'][n]['rank']['selection']['columns'],r['models'][n]['rank']['selection']['rank'],
            r['models'][n]['rank']['selection']['scaled_condition'],
            r['models'][n]['inference_diagnostics']['bread_scaled_condition']] for n in ('B1','B1_no_season_means','B2','B2_no_season_means')])
    put('سن جاری، تحصیلات و wave وارد نشده‌اند. همهٔ مدل‌ها همان دامی‌های cohort و سال قابل شناسایی و سه دامی فصل جاری را دارند. سال ۱۳۹۲ مرجع است و ستون ۱۳۹۷ نیز برای رفع وابستگی خطی سال/cohort حذف شده؛ هفت دامی cohort نگهداری شده‌اند. این همان نرمال‌سازی اجرای پنج‌مدلی است. هیچ تصمیم جدیدی دربارهٔ حذف دامی‌های سال در این بسته گرفته نشده است.')

    put('## تابع برآوردشده و مشتق مستقیم')
    put(r'''
برای هر مشاهده، \(y=\log x\)، \(L_j=\log p_j\)، و \(Z^s\) کنترل‌های مرکز/مقیاس‌شده هستند. همهٔ میانگین‌های خانوار روی همان سه موج و بدون وزن محاسبه می‌شوند. مرحلهٔ اول مخارج با وزن جاری survey و مشارکت/تقاضا بدون وزن تخمین زده شده‌اند.

\[
A_i=\alpha_i+\eta_i'Z^s,\qquad
\log a=a_0+A'L+\tfrac12 L'\Gamma L,\qquad
b=\exp(\beta'L),\qquad q=y-\log a,
\]
\[
g_i=A_i+\sum_j\gamma_{ij}L_j+\beta_iq+\frac{\lambda_i}{b}q^2,
\qquad h_i=g_i+\kappa_i\hat v+\omega_i\bar v.
\]

در B2، میانگین log مخارج در Z هست؛ میانگین CF در Z ترجمه‌ای نیست و فقط به‌صورت ω vbar اضافه می‌شود. در B0 و P0_matched، ω صفر است. معادلهٔ مشارکت همان Probit تجمیعی با کنترل‌های اعلام‌شده است؛ \(k_i\) شاخص خطی آن است.

\[
\mu_i=E[w_i\mid\text{controls}]
=\Phi(k_i)h_i+\delta_i\phi(k_i).
\]

مشتق‌ها با ثابت‌نگه‌داشتن میانگین‌های خانوار و CF جاری/میانگین، و با لحاظ تغییر احتمال خرید محاسبه می‌شوند:

\[
S_i=\beta_i+2\frac{\lambda_i}{b}q,
\]
\[
\frac{\partial\mu_i}{\partial y}
=\Phi(k_i)S_i+\phi(k_i)\tau_{iy}(h_i-\delta_i k_i),
\]
\[
\frac{\partial\mu_i}{\partial L_j}
=\Phi(k_i)\left[
\gamma_{ij}-S_i\left(A_j+\sum_k\gamma_{jk}L_k\right)
-\beta_j\frac{\lambda_i}{b}q^2\right]
+\phi(k_i)\tau_{ip_j}(h_i-\delta_i k_i).
\]

چون مقدار گروه به‌صورت \(Q_i=x\mu_i/p_i\) تعریف می‌شود:

\[
e_{ix}=1+\frac{\partial\mu_i/\partial y}{\mu_i},\qquad
e^M_{ij}=\frac{\partial\mu_i/\partial L_j}{\mu_i}-1(i=j).
\]

این مشتق‌ها اختراع یک estimator تازه نیستند: مشتق همان تابعی هستند که در مرحلهٔ دوم برازش شده است. جبر QUAIDS و بخش پایهٔ مشتق S&Y از pyquaidsce استفاده می‌شود و اصلاح مربوط به ترجمهٔ alpha و CF جمعی در لایهٔ پروژه اضافه شده است. صحت آن با تغییر عددی هر ۱۲ log قیمت و log مخارج در خود تابع برازش‌شده بررسی شده است.

کشش‌ها شرطی‌اند: تغییر جاری مخارج به معنای ثابت‌بودن CF و میانگین مخارج است، نه شوکی که خودبه‌خود این کنترل‌ها را بازحساب کند. در استنباط، عدم‌قطعیت برآورد CF و Probit منتقل می‌شود؛ ثابت‌بودن کنترل در مشتق اقتصادی با ثابت‌فرض‌کردن مرحلهٔ اول در محاسبهٔ SE متفاوت است.
''')
    put('### سه نوع خلاصهٔ مستقیم؛ تفسیر یکسان ندارند')
    table(['خلاصه','تعریف و کاربرد'],[
        ['نقطهٔ متوسط','log قیمت، log مخارج و کنترل‌های خام در میانگین حسابی نمونه؛ Phi(mean k)، phi(mean k)، و سهم پیش‌بینی‌شدهٔ واقعی mu در مخرج. این یک خانوار نماینده با دامی‌های کسری است، نه میانگین کشش خانوارها.'],
        ['مشاهده به مشاهده','مشتق برای تمام ۱۳۷٬۸۱۴ مشاهده؛ کشش لگاریتمی فقط در mu>0 تعریف می‌شود. میانگین، میانه، صدک‌ها و همهٔ ماتریس‌ها بدون بریدن یا winsorize ذخیره می‌شوند.'],
        ['مقدار تجمیعی نمونه','مشتق مجموع Q_i=sum exp(y-L_i)*mu_i؛ تمام سهم‌های برازش‌شده حتی سهم منفی در جمع نگهداری می‌شوند. این خلاصه وزن مقداری ضمنی دارد و ناپایداری تقسیم بر سهم کوچک هر خانوار را کاهش می‌دهد. وزن survey اعمال نشده است.']])
    put('روش قبلی pyquaidsce از میانگین سهم‌های مشاهده‌شده و میانگین Phi/PDF استفاده می‌کرد؛ Phi(mean k) نیز عموماً برابر mean Phi(k) نیست. بنابراین تفاوت روش قبلی و مستقیم فقط عوض‌شدن یک عدد در مخرج نیست. هر دو روش برای مقایسهٔ داخلی مدل‌ها حفظ شده‌اند، اما برای مشتق تابع برازش‌شده، تعریف مستقیم روشن‌تر است.')
    put('مقدار تجمیعی گروه برحسب شاخص exp/p_group است؛ آن را کیلوگرم واقعی سبد ناهمگن گروه تعبیر نمی‌کنیم. کشش تجمیعی، پاسخ به تغییر هم‌زمان قیمت یا مخارج در مشاهدات نمونه با ثابت‌ماندن کنترل‌هاست. برای خلاصه‌های مشاهده‌ای و تجمیعی فقط مقدار توصیفی گزارش شده، نه فاصلهٔ اطمینان.')
    put('در raw S&Y، جمع mu دقیقاً یک نیست. ماتریس موسوم به Hicksian در این بسته فقط diagnostic اسلاتسکی است: eH=eM+e_x*mu_j در نقطهٔ متوسط. این نام به معنی اثبات وجود تقاضای جبرانی سازگار با یک مدل مطلوبیت کامل نیست. قیود نظری بخش نهفته حفظ شده و قید انحنا اعمال نشده است.')

    put('## کشش‌های اصلی مستقیم، برآورد و CI۹۵٪')
    names = ('P0_matched','B0','B1','B1_no_season_means','B2','B2_no_season_means')
    for kind,title in [('expenditure','مخارج'),('marshallian','قیمت خودی')]:
        put('### '+title); rows=[]
        for i,g in enumerate(GROUPS):
            vals=[]
            for n in names:
                a=np.asarray(direct(n)['point'][kind]); se=np.asarray(direct(n)['standard_errors'][kind])
                vals.append(ci(a[i] if kind=='expenditure' else a[i,i],se[i] if kind=='expenditure' else se[i,i]))
            rows.append([g]+vals)
        table(['گروه']+list(names),rows)

    put('## اختلاف دو مدل، با لحاظ همبستگی ناشی از خانوارهای مشترک')
    put('برای هر زوج، ابتدا سهم هر خانوار در عدم‌قطعیت دو مدل تفاضل شده است. در نتیجه CF مشترک در مقایسهٔ همسان Pooled/B0 و همبستگی سایر مراحل در SE اختلاف لحاظ می‌شود. اصلاح Holm روی ۲۴ اختلاف اصلی، یعنی ۱۲ مخارج و ۱۲ خودی هر مقایسه، انجام شده است.')
    for convention,keyname in [('مشتق مستقیم','comparisons_direct'),('روش قبلی پکیج','comparisons_native')]:
        put('### '+convention)
        for key,c in r[keyname].items():
            put('#### '+key); de=c['difference_expenditure']; dp=np.diag(c['difference_marshallian'])
            se=c['standard_error_expenditure']; sp=np.diag(c['standard_error_marshallian']); p=c['pvalue_main24_holm']
            table(['گروه','اختلاف مخارج [CI95]','p Holm','اختلاف خودی [CI95]','p Holm'],
                  [[g,ci(de[i],se[i]),p[i],ci(dp[i],sp[i]),p[12+i]] for i,g in enumerate(GROUPS)])
    put('تمام اختلاف‌های متقاطع ۱۲×۱۲ همراه SE و CI در results.json ذخیره شده‌اند؛ ماتریس کشش هر مدل در ادامه آمده است.')

    put('## پایداری تقسیم بر سهم پیش‌بینی‌شده و بررسی مشاهده‌ای')
    put('اگر mu<=0 باشد، لگاریتم مقدار پیش‌بینی‌شده تعریف نمی‌شود و کشش آن مشاهده گزارش نمی‌شود؛ خود مشاهده در تخمین می‌ماند. کوچک‌بودن سهم مثبت هم می‌تواند کشش بسیار بزرگ بسازد. تعداد mu<1e-6 و |کشش مخارج|>100 صرفاً flag است و هیچ مقداری براساس این آستانه‌ها حذف یا بریده نشده است. این مشکل را با خواندن میانه/صدک‌ها و خلاصهٔ مقداری در کنار میانگین بررسی می‌کنیم.')
    put()
    put('یک نمونهٔ واقعی: در B2، کشش مخارج نان و غلات در نقطهٔ متوسط با حذف میانگین فصل تقریباً ثابت می‌ماند، اما میانگین سادهٔ کشش‌های مشاهده‌ای از حدود ۰٫۱۱ به ۰٫۰۵ می‌رود. فقط ۳۲ مشاهدهٔ این گروه |کشش مخارج|>۱۰۰ دارند و کمینه تا حدود −۸۲۰۶ می‌رسد؛ میانه حدود ۰٫۳۷ و کشش مقدار تجمیعی حدود ۰٫۳۵، تقریباً ثابت‌اند. بنابراین میانگین سادهٔ بدون برش را مبنای انتخاب تصریح قرار نمی‌دهیم؛ این مشکل مدل در دنبالهٔ پیش‌بینی‌ها باید در گزارش نهایی نیز آشکار بماند.')
    for n in ('B1','B2','B1_no_season_means','B2_no_season_means'):
        d=direct(n); micro=d['micro']; ex=micro['individual_expenditure']; ow=micro['individual_marshallian']; aq=micro['aggregate_quantity_marshallian']
        put('### '+n)
        table(['گروه','mu نامثبت','mu مثبت <1e-6','|e مخارج|>100','میانگین مخارج','میانه مخارج','p5','p95','مخارج تجمیعی','میانگین خودی','میانه خودی','خودی تجمیعی'],
              [[g,micro['nonpositive_fitted_share_count'][i],micro['positive_share_below_1e_6_count'][i],
                micro['individual_abs_expenditure_over_100_count'][i],ex['mean'][i],ex['median'][i],ex['p05'][i],ex['p95'][i],
                micro['aggregate_quantity_expenditure'][i],ow['mean'][i][i],ow['median'][i][i],aq[i][i]] for i,g in enumerate(GROUPS)])
    put('## اعتبار عددی و استنباط')
    table(['مدل','مشاهدهٔ کنترل مشتق','بیشترین خطای مطلق مشتق','بیشترین خطای مقیاس‌شده','اختلاف گام gradient SE'],
          [[n,direct(n)['validation']['current_input_numeric_derivative']['observations_checked'],
            direct(n)['validation']['current_input_numeric_derivative']['max_absolute_error'],
            direct(n)['validation']['current_input_numeric_derivative']['max_error_scaled_by_one_plus_derivative'],
            direct(n)['validation']['parameter_delta_gradient_max_step_difference']] for n in names])
    put('SE نقطهٔ متوسط از همان sandwich چندمرحله‌ای اجرای قبلی گرفته شده: RF مخارج، ۱۲ Probit، معادلات IFGNLS و به‌روزرسانی ۷۸ جزء Sigma. خوشه panel_id است. مشتق دوم واقعی score و انتقال عدم‌قطعیت CF جاری/میانگین و احتمال خرید حفظ شده است. برای مدل‌های قدیمی فقط این محاسبات استنباطی از fitted object بازیابی شده‌اند و covariance بازیابی‌شده با covariance ذخیره‌شده تطبیق داده شده است.')
    put()
    put('۲۷ آزمون کد، شامل perturbation مستقل قیمت/مخارج، کنترل انتقال RF به CF جاری/میانگین و مشتق مقدار تجمیعی، موفق‌اند. همسانی نمونه و قیمت‌ها، حفظ تک‌تک نتایج قدیمی، همهٔ قیود پارامتری و متناهی‌بودن خروجی‌های کشش/SE نیز کنترل شده‌اند. هر ۱۲ کشش خودی مستقیم در نقطهٔ متوسط در هر شش مدل منفی است؛ این کنترل، ادعای انحنای سراسری در تمام مشاهدات نیست.')
    put('عدم‌قطعیت ساخت قیمت و انتخاب نقطهٔ مرجع تجربی وارد SE نشده است؛ مرکز/مقیاس‌ها و ورودی‌های نقطهٔ مرجع نیز ثابت‌اند. فاصله‌ها نقطه‌ای و برمبنای تقریب بزرگ‌نمونه‌اند. این اجرا bootstrap نهایی مقاله نیست.')
    put('هر سه fit معیارهای یکسان native IFGNLS/GN دارند؛ به‌دلیل حذف میانگین فصل یا افزودن مشتق مستقیم، هیچ آستانه‌ای سخت‌تر نشده است. نقاط شروع از مدل نزدیک قبلی گرفته شده‌اند؛ در مدل بدون میانگین فصل فقط برای شروع، ضرایب جاری/میانگین فصل در ضریب جاری ادغام شده‌اند. تخمین نهایی آزاد است و این ادغام یک قید نهایی نیست.')
    put('همهٔ Probitها مدل تجمیعی با کنترل‌های Mundlak هستند، نه random-intercept RE-Probit. همچنان اعتبار ابزارهای درآمد و کافی‌بودن تابع کنترل خطی فرض‌های اقتصادی‌اند؛ معناداری CF یا بهبود برازش به‌تنهایی این فرض‌ها را اثبات نمی‌کند. در B2، کنترل میانگین مخارج درون‌زا هم به اعتبار سازوکار CF/ابزارهای میانگین وابسته است.')

    put('## نمونه و قیمت‌ها')
    sample=r['sample']
    table(['معیار','ردیف حذف‌شده','باقی‌مانده'],[[v['criterion'],v['new_excluded_rows'],v['remaining_rows']] for v in sample['flow']])
    put(f"هر مدل {sample['estimation_rows']:,} خانوار–سال و {sample['estimation_panels']:,} خانوار با سه سال متوالی دارد. Hash مرتب‌سازی panel_id/year: `{sample['sample_hash']}`.")
    put(f"SHA256 قیمت‌دار: `{r['priced_panel_sha256']}`. سبد ۱۰۶ قلم/۱۲ گروه، حذف نوشابه به درخواست قبلی کاربر، donor pool همهٔ ۴۳۸٬۵۷۷ مشاهده، Young و minimum support=3 همان اجرای قبلی‌اند. برای audit قیمت به [گزارش ساخت قیمت](../initial/report.md) مراجعه کنید. هیچ دادهٔ منبع یا قیمت بازار دوباره ساخته نشده است.")

    put('## پیوست: تمام ضرایب و ماتریس‌های سه تخمین جدید')
    for n in NEW:
        m=r['models'][n]; c=m['coefficients']; se=c['standard_errors']; put('## '+n)
        s=m['specification']
        for label,key in [('کنترل‌های جاری و سن مشترک','level_controls'),('میانگین‌های Mundlak','mundlak_controls'),('میانگین‌های فقط RF','rf_only_means'),('CF جمعی','additive_cf_controls')]:
            put(label+': '+(', '.join(s[key]) or 'ندارد')+'.'); put()
        table(['معیار همگرایی/اجرایی','مقدار'],list(m['convergence'].items())+list(m['numerical_settings'].items())+
              [('fixed_a0',m['fixed_a0']),('demand_parameters',m['parameters']['demand']),('Probit_parameters_each',m['parameters']['probit_each']),
               ('RF_parameters',m['parameters']['reduced_form']),('scaled_GN_ratio',m['inference_diagnostics']['gradient_scaled_gn_ratio']),
               ('bread_scaled_min_eigenvalue',m['inference_diagnostics']['bread_scaled_min_eigenvalue']),
               ('bread_scaled_condition',m['inference_diagnostics']['bread_scaled_condition'])])
        put('objective با Sigma خود هر مدل محاسبه شده و در fixed point تقریباً N×۱۲ است؛ برای رتبه‌بندی برازش از این عدد استفاده نمی‌کنیم. SSE/RMSE سهم و پایداری اقتصادی مقایسه شده‌اند. log likelihood باقیمانده نیز likelihood مشترک کامل همهٔ مراحل نیست.')
        table(['قید','مقدار'],m['restrictions'].items())
        table(['آزمون','آماره','df موثر','قید اسمی','p'],
              [[k,v.get('statistic','—'),v.get('df','—'),v.get('nominal_restrictions','—'),v.get('pvalue','—')] for k,v in m['tests'].items() if not v.get('not_applicable')])
        put('آزمون تمام میانگین‌های Mundlak در B1/B2 شامل حذف کنترل mean_head_age نیز هست؛ آن را آزمون خالص استقلال اثر خانوار تعبیر نمی‌کنیم. در P0_matched این سن آگاهانه کنترل مشترک است. p عددی صفر ناشی از محدودیت نمایش احتمال بسیار کوچک است.')
        put('### مرحلهٔ اول مخارج')
        rf=m['first_stage']
        table(['معیار','مقدار'],[(k,rf[k]) for k in ['r_squared','excluded_partial_r_squared','excluded_classical_f','income_center']])
        table(['متغیر','ضریب','SE خوشه‌ای'],[[k,v,se['reduced_form'][k]] for k,v in c['reduced_form'].items()])
        put('### پارامترهای اصلی تقاضا؛ ضریب (SE چندمرحله‌ای)')
        fields=['alpha_at_center','beta','lambda','delta','cf_current']+(['cf_mean'] if 'cf_mean' in c else [])
        table(['گروه']+fields,[[f'G{i+1}']+[f"{c[k][i]:.7g} ({se[k][i]:.7g})" for k in fields] for i in range(12)])
        matrix('Gamma',c['gamma']); matrix('SE Gamma',se['gamma'])
        matrix('تمام ضرایب کنترل در واحد اصلی',c['controls_original_units'],c['control_names'])
        matrix('SE کنترل‌ها',se['controls_original_units'],c['control_names'])
        table(['کنترل','نوع ورود','مرکز','مقیاس'],zip(c['control_names'],c['control_types'],c['control_centers'],c['control_scales']))
        matrix('تمام ضرایب ۱۲ Probit',np.asarray(c['probit']).T,c['probit_names'])
        matrix('SE Probit',np.asarray(se['probit']).T,c['probit_names'])
        table(['گروه','نرخ خرید','همگرایی','گام','کمینه Phi','بیشینه Phi'],
              [[f"G{v['group']}",v['participation_rate'],v['converged'],v['iterations'],v['Phi_min'],v['Phi_max']] for v in m['selection_diagnostics']])
        table(['گروه','مخارج قبلی','SE','مخارج نهفته قبلی','SE'],
              [[f'G{i+1}',m['elasticities']['expenditure'][i],m['elasticity_standard_errors']['expenditure'][i],
                m['elasticities']['latent_expenditure'][i],m['elasticity_standard_errors']['latent_expenditure'][i]] for i in range(12)])
        for key,title in [('marshallian','Marshallian قبلی'),('hicksian_slutsky_convention','اسلاتسکی قبلی'),('latent_marshallian','Marshallian نهفته قبلی')]:
            matrix(title,m['elasticities'][key]); matrix('SE '+title,m['elasticity_standard_errors'][key])
        matrix('Sigma خطاهای سیستم',m['error_covariance'])
    put('ضرایب کامل B0، B1 و B2 بدون تغییر در [پیوست گزارش پنج اجرا](../specification_suite/report.md) باقی مانده‌اند و در results.json این بسته نیز موجودند.')

    put('## پیوست: تمام ماتریس‌های مستقیم مدل‌های قدیمی و جدید')
    for n in names:
        d=direct(n); micro=d['micro']; put('## مشتق مستقیم '+n)
        table(['گروه','mu در نقطهٔ متوسط','Phi در mean index','PDF در mean index','مخارج مستقیم','SE','مخارج نهفته','SE نهفته'],
              [[f'G{i+1}',d['reference_diagnostics']['predicted_shares'][i],d['reference_diagnostics']['selection_cdf_at_mean_index'][i],
                d['reference_diagnostics']['selection_pdf_at_mean_index'][i],d['point']['expenditure'][i],d['standard_errors']['expenditure'][i],
                d['point']['latent_expenditure'][i],d['standard_errors']['latent_expenditure'][i]] for i in range(12)])
        put('جمع سهم پیش‌بینی‌شده در نقطهٔ متوسط: '+fmt(d['reference_diagnostics']['predicted_share_sum'])+'.')
        for key,title in [('marshallian','Marshallian مستقیم'),('hicksian_slutsky_convention','اسلاتسکی diagnostic مستقیم'),('latent_marshallian','Marshallian نهفته مستقیم')]:
            matrix(title,d['point'][key]); matrix('SE '+title,d['standard_errors'][key])
        matrix('میانگین کشش Marshallian مشاهده‌ای، فقط mu>0',micro['individual_marshallian']['mean'])
        matrix('میانه کشش Marshallian مشاهده‌ای، فقط mu>0',micro['individual_marshallian']['median'])
        matrix('کشش Marshallian مقدار تجمیعی',micro['aggregate_quantity_marshallian'])
        table(['گروه','mu نامثبت','mu مثبت <1e-6','تعداد معتبر مخارج','غیرمتناهی بین مثبت‌ها','p1 مخارج','p99 مخارج','کمینه مخارج','بیشینه مخارج'],
              [[f'G{i+1}',micro['nonpositive_fitted_share_count'][i],micro['positive_share_below_1e_6_count'][i],micro['individual_expenditure']['valid_count'][i],
                micro['nonfinite_expenditure_elasticity_among_positive_shares'][i],micro['individual_expenditure']['p01'][i],micro['individual_expenditure']['p99'][i],
                micro['individual_expenditure']['min'][i],micro['individual_expenditure']['max'][i]] for i in range(12)])
        put('همهٔ صدک‌ها، کمینه/بیشینه و تعداد معتبر هر درایهٔ متقاطع در results.json ذخیره شده‌اند.')
    put('## بازتولید و مسیر ادامه')
    put('برای این بسته، cache قیمت‌دار، نمونهٔ cohort و fitted objects پنج اجرای قبلی لازم‌اند؛ مسیر ساخت آن‌ها در گزارش قبلی و کد run.py/specification_suite.py ثبت شده است. داده‌ها و influenceهای خانوار خصوصی در intermediate می‌مانند. خروجی مخزن یک گزارش و یک JSON تجمیعی است.')
    put('```bash\npython -m unittest discover -s pilot/tests -p "test_*.py"\npython pilot/specification_followup/specification_followup.py --inputs intermediate/pilot_inputs --model P0_matched --threads 1 &\npython pilot/specification_followup/specification_followup.py --inputs intermediate/pilot_inputs --model B1_no_season_means --threads 1 &\npython pilot/specification_followup/specification_followup.py --inputs intermediate/pilot_inputs --model B2_no_season_means --threads 1 &\nwait\npython pilot/specification_followup/specification_followup.py --inputs intermediate/pilot_inputs --direct-old B0 B1 B2 --threads 3\npython pilot/specification_followup/specification_followup.py --inputs intermediate/pilot_inputs --assemble\npython pilot/specification_followup/write_followup_report.py\n```')
    put('برازش‌های مستقل هم‌زمان قابل اجرا هستند؛ بخش covariance با lock مشترک به‌ترتیب اجرا می‌شود تا حافظه کنترل شود. برای تخمین تازه، فقط cacheهای suite_P0_matched/suite_B1_no_season_means/suite_B2_no_season_means و follow مربوط به همین بسته را آرشیو کنید؛ cache مدل‌های قبلی نقطهٔ شروع است. بوت‌استرپ بزرگی اجرا نشده است.')
    put(f"pyquaidsce در commit `{r['pyquaidsce_commit']}` و نسخهٔ ۱٫۷٫۰ باقی مانده است. کد پکیج تغییر نکرده؛ همهٔ توسعه در لایهٔ pilot انجام شده است. نتایج ماشین‌خوان کامل در [results.json](results.json) هستند.")
    put('مرحلهٔ بعد می‌تواند آزمون جداگانهٔ ثبات beta/Gamma/lambda بین cohortها و سال‌ها باشد. در این بسته هیچ مدل پایه‌ای قفل نشده و نتایج B1/B2 هر دو برای تصمیم روش‌شناختی نگهداری شده‌اند.')
    (OUT/'report.md').write_text('\n'.join(lines)+'\n')


if __name__=='__main__': main()
