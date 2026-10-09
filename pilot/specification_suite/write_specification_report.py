"""One Persian report for five maintained common-slope specification pilots."""
# Support both direct scripts and python -m from the repository root.
if __package__ in (None, ""):
    import sys
    from pathlib import Path as _Path
    sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))

import json
from pathlib import Path
import numpy as np
from pilot.specification_suite.specification_suite import GROUPS, MODELS

ROOT = Path(__file__).parent


def main():
    r=json.loads((ROOT/'results.json').read_text());lines=[]
    def put(s=''):lines.append(str(s))
    def fmt(x):
        if isinstance(x,(float,np.floating)):return f'{x:.7g}'
        return str(x)
    def table(headers,rows):
        put();put('| '+' | '.join(headers)+' |');put('| '+' | '.join(['---']*len(headers))+' |')
        for row in rows:put('| '+' | '.join(fmt(x) for x in row)+' |')
        put()
    def matrix(title,x,labels=None):
        put('### '+title);x=np.asarray(x)
        table(['ردیف']+[f'G{i+1}' for i in range(x.shape[1])],
              [[labels[i] if labels else f'G{i+1}']+list(row) for i,row in enumerate(x)])
    def ci(value,se):return f'{value:.4f} [{value-1.96*se:.4f}, {value+1.96*se:.4f}]'
    def settings_model(m):
        s=m['specification']
        put('کنترل‌های جاری: '+', '.join(s['level_controls'])+'.')
        put('میانگین‌های Mundlak: '+(', '.join(s['mundlak_controls']) or 'ندارد')+'.')
        put('میانگین‌های فقط مرحلهٔ اول: '+(', '.join(s['rf_only_means']) or 'ندارد')+'.')
        put('CF جمعی اضافی: '+(', '.join(s['additive_cf_controls']) or 'ندارد')+'.')
        put('ترتیب دقیق ستون‌ها و مرکز/مقیاس آن‌ها در JSON نیز ذخیره شده است.')
    put('# پنج اجرای آزمایشی QUAIDS با S&Y و CF — ۲۰۲۶–۱۰–۰۹')
    put()
    put('این بسته پنج تصریح پیوست کاربر را روی نمونه و قیمت‌های یکسان اجرا می‌کند. نتایج قبلی نگهداری شده‌اند. ضرایب beta، Gamma و lambda در این پنج اجرا بین همهٔ سال‌ها و cohortها مشترک‌اند؛ هیچ آزمون جدید ناهمگنی شیب یا مدل با شیب متغیر در این بسته اجرا نشده است.')
    put()
    put('## نتیجهٔ اجرایی')
    rows=[]
    for name in MODELS:
        m=r['models'][name];c=m['convergence'];f=m['fit'];e=m['elasticities'];own=np.diag(e['marshallian'])
        rows.append([name,c['success'],m['parameters']['demand'],c['share_sse'],f['share_rmse_overall'],
                     f['negative_share_fraction_overall']*100,f['adding_up_rmse'],int((own>=0).sum())])
    table(['مدل','همگرایی','پارامتر تقاضا','SSE سهم','RMSE سهم','سهم منفی (%)','RMSE جمع‌پذیری','کشش خودی نامنفی'],rows)
    for key in ['B1_minus_B0','B2_minus_B1','B3_minus_B0','B0_minus_P0']:
        c=r['comparisons'][key]
        de=np.asarray(c['difference_expenditure']);dp=np.diag(c['difference_marshallian'])
        ie=int(np.argmax(np.abs(de)));ip=int(np.argmax(np.abs(dp)))
        put(f"{key}: بیشترین تغییر مطلق کشش مخارج برای {GROUPS[ie]} برابر {de[ie]:+.4f} و کشش خودی برای {GROUPS[ip]} برابر {dp[ip]:+.4f} است. از ۲۴ پاسخ اصلی، {sum(c['main24_ci95_outside_plus_minus_0_1'])} اختلاف با فاصلهٔ اطمینان ۹۵٪ بیرون بازهٔ ±۰٫۱ و {sum(c['main24_ci90_inside_plus_minus_0_1'])} اختلاف با فاصلهٔ اطمینان ۹۰٪ کاملاً داخل آن است. آستانهٔ ۰٫۱ فقط معیار توصیفی است، نه قاعدهٔ ازپیش‌اثبات‌شدهٔ اقتصادی.")
        put()
    put('در مقایسهٔ B2 با B1، تغییرات بزرگ و نسبتاً دقیقِ کشش مخارج به روغن، حبوبات و مغزها/خشکبار/خرما مربوط‌اند. این مقایسه اثر اضافه‌کردن سطح معمول مخارج را نشان می‌دهد؛ ورود این متغیر، مجموعهٔ شرایطی را که پاسخ جاری مخارج تحت آن سنجیده می‌شود نیز تغییر می‌دهد.')
    put()
    put('B1 با افزودن CF میانگین، از نظر آماری تغییر مهمی در ضرایب این تصحیح دارد، اما هر ۲۴ اختلاف اصلی کشش آن با B0 در معیار توصیفی ±۰٫۱ کوچک‌اند. B3 نیز از نظر این کشش‌ها تقریباً همان B0 است. بنابراین معناداری یک بلوک را با اهمیت اقتصادی تغییر کشش‌ها یکی نمی‌گیریم؛ دربارهٔ نگهداری CF میانگین باید منطق درون‌زایی هم لحاظ شود.')
    put()
    put('این مقایسه‌ها نتیجهٔ قطعی دربارهٔ درستی ابزار درآمد یا کامل‌بودن CRE نیستند. بهترشدن برازش با افزودن متغیر هم به‌تنهایی مبنای انتخاب مدل نهایی نیست. آزمون معناداری و اندازهٔ تغییر کشش‌ها باید کنار هم خوانده شوند.')
    put()
    put('## مشخصات دقیق و انتخاب‌های اجرایی')
    table(['مدل','تفاوت با B0'],[
        ['B0','پایه: درآمدِ میانگین فقط RF؛ سن فقط میانگین؛ CF فقط جاری'],
        ['B1','B0 + میانگین CF در Probit و به‌صورت جمعی داخل Phi در تقاضا'],
        ['B2','B1 + میانگین log مخارج در Probit و ترجمهٔ alpha'],
        ['B3','B0 با حذف چهار میانگین جنسیت/تأهل از تمام مراحل؛ کنترل‌های جاری باقی‌اند'],
        ['P0','کنترل‌های جاری B0؛ بدون تمام میانگین‌ها، از جمله میانگین‌های درآمد در RF']])
    put('در B3 چون جنسیت و تأهل واقعاً تغییر می‌کنند، آزمایش انجام شده است. شهری/روستایی و منطقه در هر سه مشاهدهٔ تمام خانوارهای نمونه ثابت‌اند، بنابراین فقط متغیر جاری آن‌ها نگهداری شده است.')
    put()
    put('برای P0 دستور «همان کنترل‌های جاری B0، بدون میانگین‌ها» دقیقاً اجرا شد. چون B0 سن را فقط به‌صورت میانگین دارد، P0 سن را ندارد. بنابراین تفاوت P0/B0 فقط اثر اصلاح Mundlak نیست و تفاوت کنترل سن و مرحلهٔ اول را نیز شامل می‌شود. برای مقایسه‌ای که سن دقیقاً یکسان کنترل شود، یک تصریح دیگر لازم خواهد بود؛ چنین اجرای اضافی در این بسته انجام نشده است.')
    put()
    put('دامی‌های سال و cohort هم‌زمان رتبهٔ مستقل کامل با ۱۱ دامی سال ندارند: مجموع دامی‌های سال ۱۳۹۷ تا ۱۴۰۳ برابر مجموع cohortهای ۱۳۹۷ تا ۱۴۰۱ است. سال‌های ۱۳۹۲ و ۱۳۹۷ از ستون‌های سال حذف شده‌اند و هفت دامی cohort نگهداری شده‌اند. این یک نرمال‌سازی است؛ همهٔ تغییرات سطحی سالِ قابل شناسایی همچنان در فضای طراحی موجودند. برای سال و cohort میانگین ساخته نشده و wave در هیچ مرحله‌ای نیست.')
    put()
    put('فصل ۱ مرجع است؛ سه دامی فصل جاری و سه میانگین آن‌ها در B0 تا B3 وجود دارند. فصل فقط در ۲۷ خانوار تغییر می‌کند، بنابراین تفکیک ضرایب فصل جاری و میانگین فصل عمدتاً بر همین خانوارها تکیه دارد. رتبهٔ کامل، تضمین شناسایی قوی نیست. ضرایب و خطاهای استاندارد این دو مجموعه باید با احتیاط تفسیر شوند؛ هیچ‌کدام به‌صورت پنهان حذف نشده‌اند.')
    table(['ویژگی','خانوارهای دارای تغییر از '+str(r['sample']['estimation_panels'])],r['household_change_counts'].items())
    put('## معادلات واقعاً اجراشده')
    put(r'''
برای خانوار h و سال t، y=log(x)، L_j=log(p_j)، D کنترل‌های جاری، M میانگین‌های Mundlak و z درآمد حقیقی لگاریتمی مرکز‌شده است.

مرحلهٔ اول B0 تا B3:

\[
y_{ht}=\pi_0+\pi_L'L_{ht}+\pi_D'D_{ht}+\pi_M'M_h+
\pi_1z_{ht}+\pi_2z_{ht}^2+\pi_3\bar z_h+\pi_4\overline{z^2}_h+v_{ht}.
\]

در B3 چهار میانگین جنسیت/تأهل از M حذف شده و در P0 تمام M و دو میانگین درآمد حذف می‌شوند. میانگین درآمد و میانگین مربع آن به Probit و QUAIDS نمی‌روند. میانگین مربع با مربع میانگین متفاوت است. RF با WLS و وزن جاری survey تخمین زده می‌شود؛ میانگین خانوار میانگین حسابی بدون وزن سه موج است.

\[
\hat v_{ht}=y_{ht}-\hat y_{ht},\qquad
\bar v_h=\tfrac13\sum_t\hat v_{ht},\qquad
\bar y_h=\tfrac13\sum_t y_{ht}.
\]

برای هر گروه یک Probit جدا با log قیمت‌های جاری، log مخارج جاری، D، M و CF جاری اجرا می‌شود. B1 و B2 علاوه بر آن vbar، و B2 همچنین ybar را دارند. درآمد جاری و میانگین درآمد مستقیماً در این معادلات نیستند. همهٔ Probitها تجمیعی با کنترل‌های Mundlak هستند؛ random-intercept integration یا joint RE likelihood اجرا نشده است.

در معادلهٔ تقاضا Z شامل D و M است و در B2، ybar هم به آن اضافه می‌شود. Z مرکز/مقیاس‌بندی می‌شود:

\[
A_{iht}=\alpha_i+\theta_i'Z^s_{ht},
\]
\[
\ln a_{ht}(p)=a_0+\sum_j A_{jht}L_{jht}
+\tfrac12\sum_j\sum_k\gamma_{jk}L_{jht}L_{kht},
\qquad b(p)=\exp(\beta'L),\qquad q=y-\ln a(p),
\]
\[
g_{iht}=A_{iht}+\sum_j\gamma_{ij}L_{jht}+\beta_iq_{ht}
+\frac{\lambda_i}{b(p_{ht})}q_{ht}^2.
\]

معادلهٔ نهایی:

\[
w_{iht}=\Phi(\hat k_{iht})
\left[g_{iht}+\kappa_i\hat v_{ht}+\omega_i\bar v_h\right]
+\delta_i\phi(\hat k_{iht})+u_{iht}.
\]

omega فقط در B1 و B2 آزاد است. برخلاف مدل قبلی، vbar در این بسته alpha یا شاخص قیمت را تغییر نمی‌دهد؛ فقط یک تصحیح جمعی، داخل Phi، است. برای آن تقسیم بر SD انجام می‌شود ولی مرکزسازی نمی‌شود؛ ضرایب original units در گزارش اثر بر حسب باقیماندهٔ خام هستند.

قیود: مجموع alpha برابر یک؛ مجموع beta، lambda، kappa، omega و ضرایب هر کنترل ترجمه‌ای برابر صفر؛ Gamma متقارن با جمع سطر صفر است. deltaهای S&Y آزادند. مجموع سهم‌های نهفته یک است، اما سهم‌های مشاهده‌شدهٔ پیش‌بینی‌شدهٔ raw S&Y الزاماً جمع یک ندارند. قید انحنا اعمال نشده است.

ثابت‌بودن beta/Gamma/lambda به معنی ثابت‌بودن کشش‌ها نیست. همچنین ترجمهٔ alpha در شاخص قیمت وارد می‌شود، بنابراین کنترل سطح در این مدل غیرخطی، همان عرض از مبدأ مستقل از قیمت در یک رگرسیون خطی نیست.
''')
    put('## نمونه و قیمت‌های ثابت')
    sample=r['sample']
    table(['معیار','ردیف حذف‌شدهٔ جدید','ردیف باقی‌مانده'],[[x['criterion'],x['new_excluded_rows'],x['remaining_rows']] for x in sample['flow']])
    put(f"نمونهٔ هر مدل: {sample['estimation_rows']:,} خانوار–سال و {sample['estimation_panels']:,} خانوار با دقیقاً سه سال متوالی. hash ترتیب panel_id/year: `{sample['sample_hash']}`.")
    put(f"SHA256 فایل قیمت‌دار: `{r['priced_panel_sha256']}`. بازار قیمت، پاک‌سازی، سبد ۱۰۶قلمی و روش Young تغییر نکرده‌اند. price donor pool همان All با ۴۳۸٬۵۷۷ مشاهده است. توضیح و پوشش tierهای قیمت در [گزارش پیشین](../initial/report.md) و نتایج منبع در [results_cohort.json](../cohort/results.json) موجود است. هیچ ردیف یا ستون منبع بازنویسی نشده است.")
    put('## استنباط و معنای مقایسه‌ها')
    put('از sandwich معادلات برآوردِ روی‌هم‌قرارگرفته استفاده شده است: WLS مخارج، ۱۲ Probit، IFGNLS تقاضا و ۷۸ مؤلفهٔ مستقل Sigma. مشتق‌های score واقعی شامل مشتق دوم تقاضا و بازخورد برآورد Sigma هستند. عدم‌قطعیت CF جاری، CF میانگین و احتمال‌های خرید منتقل شده است. خوشهٔ استنباط panel_id است و هر سه مشاهده با هم قرار می‌گیرند. بوت‌استرپ انجام نشده؛ عدم‌قطعیت قیمت‌های ساخته‌شده و نقطهٔ مرجع تجربی در این استنباط وارد نشده است.')
    put()
    put('چون سن فقط به‌صورت mean_head_age وارد شده، آزمون مشترک تمام میانگین‌های Mundlak حذف کنترل سن را هم آزمون می‌کند؛ آن را آزمون خالص استقلال اثر خانوار از متغیرها معرفی نمی‌کنیم.')
    put()
    put('آزمون‌های جدول، Wald چندمرحله‌ای خوشه‌ای هستند، نه آزمون‌های ساده با ثابت‌فرض‌کردن مراحل قبلی. آزمون بلوک تقاضا، مشارکت و آزمون مشترک هر دو جدا گزارش شده‌اند. این آزمون‌ها را نباید آزمون علیت یا اعتبار ابزار دانست. برای اختلاف کشش دو مدل، influence function همان خانوار در دو مدل تفاضل شده است؛ خطای استاندارد دو مدل مستقل فرض نشده است. در ۲۴ اختلاف اصلی هر مقایسه، p-value خام و تصحیح Holm ذخیره شده‌اند.')
    put()
    put('کشش‌ها convention فعلی pyquaidsce در میانگین‌های نمونه را نگه می‌دارند: از میانگین سهم‌های مشاهده‌شده و میانگین CDF/PDF استفاده می‌شود. این دقیقاً کششِ مشتقِ سهم پیش‌بینی‌شده در یک خانوار فرضی نیست. meanهای Mundlak، میانگین مخارج و CF در مشتق جاری ثابت‌اند؛ اثر جاری قیمت/مخارج بر احتمال خرید لحاظ می‌شود. Hicksian گزارش‌شده از convention اسلاتسکی پکیج است و با توجه به raw S&Y، اثبات تقاضای جبرانی یک مدل مطلوبیت کامل نیست.')
    put('## مقایسهٔ کشش‌های اصلی')
    for kind,title in [('expenditure','کشش مخارج'),('marshallian','کشش خودی Marshallian')]:
        rows=[]
        for i,g in enumerate(GROUPS):
            values=[]
            for name in MODELS:
                m=r['models'][name];e=np.asarray(m['elasticities'][kind]);s=np.asarray(m['elasticity_standard_errors'][kind])
                values.append(ci(e[i] if kind=='expenditure' else e[i,i],s[i] if kind=='expenditure' else s[i,i]))
            rows.append([f'G{i+1}: {g}']+values)
        put('### '+title+'؛ برآورد و فاصلهٔ اطمینان ۹۵٪');table(['گروه']+list(MODELS),rows)
    put('## اختلاف کشش‌ها با لحاظ همبستگی دو مدل')
    for key,c in r['comparisons'].items():
        put('### '+key)
        de=np.asarray(c['difference_expenditure']);dp=np.diag(c['difference_marshallian'])
        se=np.asarray(c['standard_error_expenditure']);sp=np.diag(c['standard_error_marshallian'])
        p=c['pvalue_main24_holm']
        table(['گروه','اختلاف مخارج [CI95]','p مخارج Holm','اختلاف خودی [CI95]','p خودی Holm'],
              [[g,ci(de[i],se[i]),p[i],ci(dp[i],sp[i]),p[12+i]] for i,g in enumerate(GROUPS)])
    put('## کشش‌های متقاطع منتخب')
    put('ردیف پاسخ تقاضای گروه و ستون قیمت گروه دیگر است. برای موضوع کالاهای قندی، دو جهت رابطهٔ G10 با G9، G11 و G4 و نیز رابطهٔ نوشیدنی و لبنیات گزارش می‌شود؛ تمام روابط در ماتریس‌های کامل پایین و JSON موجودند. انتخاب روابط براساس موضوع است، نه براساس p-value نتایج.')
    pairs=[(9,8),(8,9),(9,10),(10,9),(9,3),(3,9),(10,3),(3,10)]
    table(['تقاضا ← قیمت']+list(MODELS),
          [[f'G{i+1} ← G{j+1}']+[ci(r['models'][n]['elasticities']['marshallian'][i][j],r['models'][n]['elasticity_standard_errors']['marshallian'][i][j]) for n in MODELS] for i,j in pairs])
    put('### اختلاف کشش‌های متقاطع منتخب؛ برآورد و CI95 زوجی')
    keys=list(r['comparisons'])
    table(['تقاضا ← قیمت']+keys,
          [[f'G{i+1} ← G{j+1}']+[ci(r['comparisons'][k]['difference_marshallian'][i][j],r['comparisons'][k]['standard_error_marshallian'][i][j]) for k in keys] for i,j in pairs])
    put('## جزئیات هر مدل: همهٔ ضرایب و ماتریس‌ها')
    for name in MODELS:
        m=r['models'][name];put('## '+name);settings_model(m)
        c=m['convergence'];d=m['inference_diagnostics']
        table(['معیار','مقدار'],list(c.items())+[(k+'_parameters',v) for k,v in m['parameters'].items()]+list(m['numerical_settings'].items())+
              [('multistage_bread_scaled_min_eigenvalue',d['bread_scaled_min_eigenvalue']),
               ('multistage_bread_scaled_condition',d['bread_scaled_condition']),
               ('scaled_GN_ratio',d['gradient_scaled_gn_ratio']),
               ('delta_gradient_step_difference',d['elasticity_delta_gradient_max_step_difference']),
               ('selection_rank',m['rank']['selection']['rank']),
               ('selection_columns',m['rank']['selection']['columns']),
               ('selection_scaled_condition',m['rank']['selection']['scaled_condition'])])
        put('مدل شروع عددی: '+m['starting_model']+'. شروع نزدیک برای صرفه‌جویی محاسباتی است؛ معیار توقف در تمام مدل‌ها یکسان است.')
        put('در نقطهٔ ثابت IFGNLS، وقتی Sigma=u′u/N است، مجموع خطای مربعی وزن‌دار تقریباً N×۱۲=۱٬۶۵۳٬۷۶۸ می‌شود. نزدیک‌بودن objective پنج مدل به این عدد طبیعی است و نشان‌دهندهٔ یکسان‌بودن برازش آن‌ها نیست.')
        put('مقدار objective برحسب Sigma برآوردشدهٔ همان مدل است و هدف IFGNLS با به‌روزرسانی Sigma تغییر می‌کند؛ آن را مستقیماً معیار رتبه‌بندی پنج مدل قرار ندهید. log_likelihood یک شاخص نرمال مبتنی بر باقیماندهٔ سیستم است، نه likelihood مشترک کامل مراحل.')
        table(['قید','مقدار'],m['restrictions'].items())
        table(['گروه','RMSE سهم','سهم منفی (%)','میانگین مشاهده‌شده','میانگین پیش‌بینی‌شده'],
              [[f'G{i+1}',m['fit']['share_rmse_by_group'][i],100*m['fit']['negative_share_fraction_by_group'][i],m['fit']['mean_observed_shares'][i],m['fit']['mean_fitted_shares'][i]] for i in range(12)])
        put('### آزمون‌های چندمرحله‌ای')
        table(['آزمون','آماره','df موثر','تعداد قید اسمی','p'],
              [[k,v.get('statistic','—'),v.get('df','—'),v.get('nominal_restrictions','—'),v.get('pvalue','—')] for k,v in m['tests'].items() if not v.get('not_applicable')])
        put('در صورت افت رتبهٔ covariance آزمون، df موثر و تعداد قید اسمی جدا گزارش شده‌اند؛ p برابر صفر در JSON ناشی از محدودیت نمایش عددی است، نه احتمال ریاضی دقیقاً صفر.')
        put('### مرحلهٔ اول مخارج')
        rf=m['first_stage']
        table(['معیار','مقدار'],[(k,rf[k]) for k in ['r_squared','excluded_partial_r_squared','excluded_classical_f','income_center']])
        coeff=m['coefficients'];se=coeff['standard_errors']
        table(['متغیر RF','ضریب','SE خوشه‌ای'],[[k,v,se['reduced_form'][k]] for k,v in coeff['reduced_form'].items()])
        put('### ضرایب اصلی QUAIDS؛ برآورد (SE چندمرحله‌ای)')
        fields=['alpha_at_center','beta','lambda','delta','cf_current']
        if 'cf_mean' in coeff: fields.append('cf_mean')
        table(['گروه']+fields,[[f'G{i+1}']+[f"{coeff[k][i]:.7g} ({se[k][i]:.7g})" for k in fields] for i in range(12)])
        matrix('Gamma — تمام ضرایب قیمت',coeff['gamma']);matrix('SE چندمرحله‌ای Gamma',se['gamma'])
        matrix('کنترل‌های تقاضا در واحد اصلی؛ نوع ورود در جدول بعد',coeff['controls_original_units'],coeff['control_names'])
        matrix('SE چندمرحله‌ای کنترل‌های تقاضا',se['controls_original_units'],coeff['control_names'])
        table(['متغیر','نوع ورود','مرکز','مقیاس'],zip(coeff['control_names'],coeff['control_types'],coeff['control_centers'],coeff['control_scales']))
        matrix('تمام ضرایب ۱۲ Probit',np.array(coeff['probit']).T,coeff['probit_names'])
        matrix('SE چندمرحله‌ای ضرایب Probit',np.array(se['probit']).T,coeff['probit_names'])
        table(['گروه','نرخ خرید','همگرایی Probit','تعداد گام','کمینه Phi','بیشینه Phi'],
              [[f"G{p['group']}",p['participation_rate'],p['converged'],p['iterations'],p['Phi_min'],p['Phi_max']] for p in m['selection_diagnostics']])
        table(['گروه','کشش مخارج','SE','کشش مخارج نهفته','SE نهفته'],
              [[f'G{i+1}',m['elasticities']['expenditure'][i],m['elasticity_standard_errors']['expenditure'][i],m['elasticities']['latent_expenditure'][i],m['elasticity_standard_errors']['latent_expenditure'][i]] for i in range(12)])
        for key,title in [('marshallian','Marshallian'),('hicksian_slutsky_convention','Hicksian با convention اسلاتسکی'),('latent_marshallian','Marshallian نهفته')]:
            matrix('ماتریس کامل کشش '+title,m['elasticities'][key])
            matrix('SE چندمرحله‌ای ماتریس '+title,m['elasticity_standard_errors'][key])
        matrix('ماتریس covariance خطاهای سیستم، Sigma',m['error_covariance'])
    put('## محدودیت روش‌شناختی و نحوهٔ بازتولید')
    put('اجزای QUAIDS، S&Y و Mundlak از ادبیات و هستهٔ pyquaidsce آمده‌اند؛ انتخاب مجموعهٔ میانگین‌ها و CF دوبخشی، توسعهٔ پروژه است. این پنج اجرا آزمون حساسیت‌اند، نه اثبات سازگاری یک CRE غیرخطی کامل. اعتبار حذف اثر مستقیم درآمد، کافی‌بودن residual inclusion خطی و باقی‌ماندن ناهمگنی خانوار در جزء درجهٔ دوم هنوز فرض‌های اقتصادی قابل بررسی‌اند. ورود هم‌زمان ybar و vbar در B2 با رتبهٔ کامل ممکن شد، اما رتبهٔ کامل اعتبار اصلاح درون‌زایی ybar را اثبات نمی‌کند. معنای ساختاری نتایج B2 به اعتبار ابزارهای درآمد میانگین نیز وابسته است.')
    put()
    put('در این بسته هیچ قید انحنا، حذف سال/گروه، تغییر منبع قیمت یا bootstrap افزوده نشده است. کشش خودی مثبت، سهم پیش‌بینی‌شدهٔ منفی، SE بزرگ و condition بالا باید گزارش شوند؛ همگرایی عددی به‌تنهایی صحت اقتصادی نیست.')
    put()
    put('```bash\nPILOT_BLAS_THREADS=3 python pilot/specification_suite/specification_suite.py --inputs intermediate/pilot_inputs\npython pilot/specification_suite/write_specification_report.py\npython -m unittest discover -s pilot/tests -p "test*.py"\n```')
    put('اگر فایل‌های مرحلهٔ قبلی موجود نیستند، ابتدا نمونه و cache قدیمی را با دستور زیر بسازید؛ خروجی قدیمی در intermediate نوشته می‌شود و نتایج قبلی مخزن بازنویسی نمی‌شوند:')
    put('```bash\nPILOT_BLAS_THREADS=3 python pilot/common/run.py --inputs intermediate/pilot_inputs --models CRE --no-year-season --cohort-instead-of-wave --cache-prefix cohort_ --stage-cache intermediate/pilot_inputs/frame_stage.pkl --warm-start pilot/cohort/results.json --output intermediate/pilot_inputs/suite_legacy_baseline.json\n```')
    put('کد از cache قیمت‌دار و نمونهٔ معتبر اجرای قبلی استفاده می‌کند؛ مراحل و fitted objects فقط در intermediate نگهداری می‌شوند. برای اجرای تازهٔ تخمین، فایل‌های suite_* در intermediate/pilot_inputs را به مسیر آرشیو منتقل کنید تا cache استفاده نشود. microdata یا influence function خانوارها وارد GitHub نشده است.')
    put(f"هستهٔ pyquaidsce در commit `{r['pyquaidsce_commit']}` ثابت است. وابستگی‌ها در `pilot/requirements.txt` ثبت شده‌اند. نتایج کامل ماشین‌خوان در [results.json](results.json) هستند.")
    (ROOT/'report.md').write_text('\n'.join(lines)+'\n')


if __name__=='__main__':main()
