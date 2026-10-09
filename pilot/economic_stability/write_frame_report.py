"""Plain Persian interpretation followed by complete reproducible result tables."""
# Support both direct scripts and python -m from the repository root.
if __package__ in (None, ""):
    import sys
    from pathlib import Path as _Path
    sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))

import json
from pathlib import Path
import numpy as np
from pilot.initial.write_report import table, matrix, GROUPS


def ptext(v): return '<1e-300' if v == 0 else f'{v:.5g}'


def economic_label(item, margin='0.1'):
    mr = item['margin_results'][margin]
    if mr['equivalent_after_holm']: return 'کوچک، با شواهد آماری'
    if mr.get('difference_beyond_margin_after_holm', False): return 'بزرگ، با شواهد آماری'
    return 'اندازه هنوز نامطمئن'


def free_names(control_names, blocks, labels, plain=False):
    n = 12; h = 11
    def names(block):
        if block == 'gamma': return [f'gamma_G{i+1}_G{j+1}' for i, j in zip(*np.triu_indices(h))]
        return [f'{block}_G{i+1}' for i in range(n if block == 'delta' else h)]
    out = [x for block in ['alpha','beta','gamma','lambda'] for x in names(block)]
    if not plain: out += names('delta')+names('cfcoef')
    for label in labels[1:]:
        out += [label+'_minus_reference__'+x for block in blocks for x in names(block)]
    out += [name+'_standardized_G'+str(i+1) for name in control_names for i in range(h)]
    return out


def main():
    root = Path(__file__).parent
    r = json.loads((root/'results_frame_stability.json').read_text())
    plain_path = root/'results_plain_stability.json'
    plain = json.loads(plain_path.read_text()) if plain_path.exists() else None
    parts = ['# پایداری زمانی ضرایب و اهمیت اقتصادی تفاوت کشش‌ها\n']
    def add(title, body): parts.append('## '+title+'\n\n'+body+'\n')
    main_test = r['tests']['beta_gamma_lambda_equal']
    ecs = r['economic_comparisons']; m = '0.1'
    significant = sum(x['pvalue_zero_holm_24'] < .05 for x in ecs)
    small = sum(x['margin_results'][m]['equivalent_after_holm'] for x in ecs)
    large = sum(x['margin_results'][m].get('difference_beyond_margin_after_holm', False) for x in ecs)
    add('خلاصهٔ اجرایی', f'''**فرض مشترک بودن ضرایب اصلی تقاضا بین ۱۳۹۲–۱۳۹۶ و ۱۳۹۷–۱۴۰۳ رد می‌شود. ولی تفاوت اقتصادی همهٔ کالاها بزرگ نیست.**

در مدل Mundlak/S&Y، با محاسبهٔ عدم‌اطمینان مرحلهٔ مخارج، هر ۱۲ معادلهٔ خرید و تخمین سیستم، آزمون سراسری برابری beta/gamma/lambda برابر {main_test['statistic']:.3f} با {main_test['df']} قید است؛ p={ptext(main_test['pvalue'])}. این بررسی bootstrap نمی‌خواهد؛ خطای استاندارد از روش شناخته‌شدهٔ معادلات تخمینِ چندمرحله‌ای به دست آمده است.

از ۲۴ مقایسهٔ اصلی (۱۲ کشش مخارج و ۱۲ کشش قیمت خود کالا)، {significant} تفاوت پس از اصلاح تعدد آزمون‌ها از نظر آماری قابل تشخیص است. با معیار نمونهٔ **۰٫۱ واحد کشش**، کوچک بودن تفاوت در {small} مورد و بزرگ‌تر بودن تفاوت از این مرز در {large} مورد با همان اصلاح تأیید می‌شود؛ برای {24-small-large} مورد شواهد برای تعیین اندازهٔ اقتصادی کافی نیست. این عدد ۰٫۱ یک انتخاب شفاف برای مقایسه است، نه قانون عمومی اقتصاد؛ معیارهای ۰٫۰۵ و ۰٫۲ هم گزارش شده‌اند.

مثال روشن: کشش مخارج برنج از ۱٫۵۸۱ به ۱٫۶۱۲ می‌رسد. تفاوت از نظر آماری قابل تشخیص است، ولی برای افزایش ۱۰درصدی مخارج فقط حدود ۰٫۳۰ واحد درصد تفاوت پاسخ تقاضاست. کشش خودی روغن از −۰٫۹۲۳ به −۰٫۱۵۳ می‌رسد؛ اختلاف پاسخ محلی به افزایش ۱۰درصدی قیمت حدود ۷٫۷ واحد درصد است. بنابراین رد آماری را نمی‌توان به «همهٔ تفاوت‌ها از نظر اقتصادی بزرگ‌اند» ترجمه کرد.

نمونه و قیمت‌ها ثابت‌اند: **۴۵٬۹۳۸ خانوار، ۱۳۷٬۸۱۴ مشاهده، ۱۰۶ قلم و ۱۲ گروه**. cohortها باقی‌اند؛ سال، فصل، wave، تحصیلات و قید انحنا وارد نشده‌اند. مرز ۱۳۹۷ تغییر مستند چارچوب نمونه‌گیری است؛ نتیجه به‌تنهایی تغییر ترجیحات یا یک علت اقتصادی خاص را اثبات نمی‌کند.''')
    add('این بار دقیقاً چه چیزی آزمایش شد؟', '''دامی cohort می‌تواند سطح تقاضای خانوارهای ورودی مختلف را جابه‌جا کند. اما به‌تنهایی نمی‌گوید پاسخ به افزایش قیمت یا مخارج برای همهٔ دوره‌ها برابر است. آزمون این بار می‌پرسد: **آیا ضرایب تعیین‌کنندهٔ این پاسخ‌ها را می‌توان در دو بازه مشترک گرفت؟**

مدل نامقید اجازه می‌دهد beta، gamma و lambda در دو بازه فرق کنند. کنترل‌های جمعیت‌شناختی، Mundlak، cohort، ضریب CF و ضریب اصلاح S&Y همچنان مشترک‌اند. هر بازه به‌طور جداگانه قیود جمع‌پذیری نهفته، همگنی و تقارن تقاضا را حفظ می‌کند. ۸۸ پارامتر تفاوت اضافه شد؛ هیچ دامی سطحی تازه‌ای برای ۱۳۹۷ یا ۱۴۰۰ اضافه نشد. اثر سطحی قبل/بعد از ۱۳۹۷ با cohortها هم‌خط است.

پس این آزمون ثبات **بلوک‌های اصلی تقاضا** است؛ آزمون ثابت بودن تمام ضرایبِ تمام مراحل یا تک‌تک ۱۲ سال نیست. مدل مقید قبلی همان پایهٔ cohort است. مراحل مخارج و خرید در مقایسه مشترک‌اند، ولی خطای تخمین آنها در خطای استاندارد مدل نامقید لحاظ شده است.''')
    add('جدول مستقیم کشش‌های مدل اصلی', table(
        ['گروه','مخارج قبل','مخارج بعد','قیمت خودی قبل','قیمت خودی بعد'],
        [[GROUPS[i], r['elasticities_common_point'][r['labels'][0]]['expenditure'][i],
          r['elasticities_common_point'][r['labels'][1]]['expenditure'][i],
          r['elasticities_common_point'][r['labels'][0]]['marshallian'][i][i],
          r['elasticities_common_point'][r['labels'][1]]['marshallian'][i][i]] for i in range(12)]))
    for kind, title in [('expenditure','مخارج'),('own_marshallian','قیمت خود کالا')]:
        rows = []
        for item in ecs:
            if item['kind'] != kind: continue
            rows.append([GROUPS[item['group']-1], item['difference_after_minus_before'], item['standard_error'],
                item['ci95'][0], item['ci95'][1], ptext(item['pvalue_zero_holm_24']),
                item['quantity_response_gap_pp_for_10pct_shock'], economic_label(item)])
        add('تفاوت کشش '+title+' — اهمیت آماری و اقتصادی', table(
            ['گروه','بعد−قبل','SE','حد پایین ۹۵٪','حد بالا ۹۵٪','p اصلاح‌شده','اختلاف پاسخ به شوک ۱۰٪؛ واحد درصد','اندازه با مرز ۰٫۱'], rows))
    add('چگونه اهمیت اقتصادی را سنجیدیم؟', '''هر دو دوره در قیمت، مخارج، سهم‌ها و ویژگی‌های خانوار **یکسان** ارزیابی شدند؛ فقط ضرایب دوره عوض شد. بنابراین جدول‌ها تغییر ترکیب نمونه یا سطح قیمت میان دوره‌ها را با تغییر ضریب مخلوط نمی‌کنند. اعداد، کشش در نقطهٔ مرجع مشترک با قرارداد فعلی pyquaidsce هستند؛ متوسط کشش واقعی تمام خانوارهای هر دوره نیستند.

برای شوک کوچک ۱۰درصدی، اختلاف کشش ×۱۰ تقریباً اختلاف پاسخ مقدار تقاضا به واحد درصد است. این تقریب محلی است؛ تغییر رفاه یا پاسخ دقیق غیرخطی به یک سیاست بزرگ نیست.

سه پرسش جدا پاسخ داده شد: (۱) آیا تفاوت صفر است؟ (۲) آیا تفاوت در بازهٔ ±مرز اقتصادی قرار دارد؟ (۳) آیا اندازهٔ تفاوت از آن مرز بیشتر است؟ پرسش دوم با آزمون معادل‌بودن دوطرفهٔ TOST بررسی شد، نه با عدم رد تفاوت صفر. برای پرسش سوم آزمون دوطرفهٔ محافظه‌کارانهٔ فراتر رفتن از مرز به کار رفت. هر خانوادهٔ ۲۴ آزمون با Holm اصلاح شد. فاصله‌های ۹۵٪ جدول، فردی‌اند؛ برچسب نهایی اندازه از p اصلاح‌شده استفاده می‌کند.

«اندازه هنوز نامطمئن» به معنی برابر بودن کشش‌ها نیست. ممکن است نقطهٔ برآورد کوچک باشد ولی خطای استاندارد برای تأیید کوچک بودن کافی نباشد؛ یا تفاوت آماری وجود داشته باشد ولی معلوم نباشد از مرز اقتصادی عبور می‌کند یا نه.''')
    sensitivity = []
    for margin in ['0.05','0.1','0.2']:
        ss = sum(x['margin_results'][margin]['equivalent_after_holm'] for x in ecs)
        ll = sum(x['margin_results'][margin].get('difference_beyond_margin_after_holm', False) for x in ecs)
        sensitivity.append([margin, ss, ll, 24-ss-ll])
    add('حساسیت به تعریف تفاوت اقتصادی', table(['مرز واحد کشش','کوچک تأییدشده','بزرگ تأییدشده','اندازه نامطمئن'], sensitivity))
    add('آزمون‌های برابری ضرایب و صفر بودن کنترل‌ها در مدل اصلی', table(['فرض صفر','Wald','تعداد قیود','p'],
        [[k,v['statistic'],v['df'],ptext(v['pvalue'])] for k,v in r['tests'].items()]))
    add('عدم‌اطمینان چگونه حساب شد؟', '''روش، sandwich معادلات تخمینِ انباشته مطابق Hardin (2002) و منطق generated regressors در Murphy–Topel (1985) است. این یک روش شناخته‌شدهٔ استنباط چندمرحله‌ای است؛ محاسبهٔ مخصوص QUAIDS حاضر از معادلات واقعی همین برآوردگر مشتق شد.

بردار معادلات شامل WLS مخارج، scoreهای ۱۲ Probit، score غیرخطی IFGNLS و ۷۸ درایهٔ مستقل covariance خطای ۱۲ معادله است. score هر سه مشاهدهٔ یک خانوار جمع می‌شود؛ covariance مجموع خانوارها همبستگی موج‌ها و همبستگی میان مراحل را حفظ می‌کند. Jacobian مشاهده‌شده شامل جملهٔ residual × مشتق دوم است؛ صرفاً تقریب Gauss–Newton به جای آن گذاشته نشده است. اثر CF جاری و میانگین CF بر طراحی Probit و تقاضا نیز وارد محاسبه شد.

این covariance نسبت به آزمون‌های conditional قبلی کامل‌تر است. همچنان قیمت‌های ساخته‌شده، متغیرهای مرجع، a0 و انتخاب مرکز/مقیاس را ثابت می‌گیرد. خطای ساخت قیمت از donor pool، طراحی کامل survey و صحت فرض حذف درآمد از معادلهٔ تقاضا با این محاسبه حل نمی‌شوند. همبستگی خانوارها در یک بازار، فراتر از خوشه‌بندی خانوار، در این اجرا جدا مدل نشده است. این محدودیت‌ها در مدل ساده‌تر هم مربوط‌اند؛ «نتیجهٔ قطعی مستقل از مدل» ادعا نمی‌کنیم.

برای کشش‌ها، delta method از covariance مشترک ضرایب تقاضا، Probit و مخارج استفاده می‌کند؛ تغییر CDF/PDF مرجع و residual تولیدشده نیز لحاظ می‌شود. هنگام گرفتن مشتق کشش نسبت به قیمت/مخارج جاری، کنترل‌های Mundlak و CF ثابت‌اند.''')
    add('معنای ماتریس‌های کشش', '''ماتریس Marshallian پاسخ به قیمت را با مخارج اسمی جاری ثابت نشان می‌دهد؛ سطر، کالای مورد تقاضا و ستون، قیمتی است که تغییر می‌کند. قطر اصلی کشش قیمت خود کالا و خارج از قطر کشش متقاطع است. ماتریس Hicksian در این پایلوت طبق هویت Slutsky و همان قرارداد pyquaidsce محاسبه شده است. چون mean مشاهده‌شدهٔ raw S&Y جمع‌پذیری دقیق ندارد، از این ماتریس بدون بررسی سازگاری بیشتر برای رفاه نهایی استفاده نمی‌کنیم. هیچ قید انحنا اعمال نشده است.''')
    add('معادلهٔ واقعی و تغییر لازم در مدل', f'''```text
R = 0 for 1392–1396; R = 1 for 1397–1403
a_i(Z) = alpha_i + Z theta_i
ln A_R = a0 + a(Z)' ln p + 0.5 ln(p)' Gamma_R ln(p)
D_R = ln x - ln A_R
f_iR = a_i(Z) + Gamma_iR ln(p) + beta_iR D_R
       + lambda_iR exp(-beta_R' ln(p)) D_R^2
E[w_i | .] = Phi(k_i) [f_iR + kappa_i vhat] + delta_i phi(k_i)
beta_R = beta_0 + R Delta_beta
Gamma_R = Gamma_0 + R Delta_Gamma
lambda_R = lambda_0 + R Delta_lambda
```

a0={r['a0']:.12g}. قیود در هر R: sum alpha=1، sum beta=sum lambda=sum kappa=0، Gamma متقارن با مجموع سطر صفر و sum theta در هر shifter صفر است. raw S&Y مجموع سهم مشاهده‌شده را دقیقاً یک تحمیل نمی‌کند.

اگر مدل نهایی هم این نتیجه را تأیید کند، انتخاب قابل دفاع این است که به جای مجبور کردن همهٔ دوره‌ها به یک beta/gamma/lambda، بلوک‌های لازم را با تعامل دوره متفاوت کنیم و کشش‌های هر دوره را جدا گزارش دهیم. لازم نیست از ابتدا برای تک‌تک ۱۲ سال مدل مستقل بسازیم. مشترک گرفتن یک بلوک باید با آزمون همان قید و اهمیت اقتصادی آن توجیه شود؛ معادل‌بودن یک کشش برای یک کالا، به‌تنهایی برابری همهٔ پارامترهای آن معادله را اثبات نمی‌کند.

به دلیل تغییر frame در ۱۳۹۷ و نبود خانوار مشترک میان دو frame، تغییر پاسخ را نمی‌توان خالصاً به گذشت زمان یا ترجیحات نسبت داد. این یک مقایسهٔ مشروط میان گروه‌ها/دوره‌هاست. year/season حذف‌شده هم می‌توانند شوک‌های زمانی جذب‌نشده باقی بگذارند.''')
    add('نمونه، کنترل‌ها و همگرایی', table(['بازه','مشاهده'],list(r['counts'].items()))+'\n'+
        table(['شرط حذف','حذف جدید','باقی‌مانده'], [[x['criterion'],x['new_excluded_rows'],x['remaining_rows']] for x in r['sample']['flow']])+'\n'+
        table(['همگرایی','مقدار'], list(r['convergence'].items()))+'\n'+
        table(['تنظیم عددی','مقدار'], list(r['numerical_settings'].items()))+'\n'+
        table(['کنترل سطحی'],[[x] for x in r['design']['level_controls']])+'\n'+
        table(['Mundlak mean بدون وزن، از سه موج'],[[x] for x in r['design']['Mundlak_variables']])+'''
CF: ln مخارج بر ۱۲ ln قیمت، کنترل‌های سطحی، ۲۰ mean برون‌زا و log درآمد جاری مرکززدایی‌شده و مربع آن با survey weight جاری رگرس می‌شود. residual جاری و میانگین خانواری residual وارد Probit و سیستم تقاضا می‌شوند. mean log مخارج به ساختار اضافه نشده است. Probit و IFGNLS قرارداد بدون وزن همان پایلوت را دارند. participation حاشیه‌ایِ Probit با meanهای Mundlak است؛ full joint random-intercept RE-Probit نامیده نمی‌شود.

کنترل‌های تقاضا، ترجمهٔ alpha و شاخص translog هستند و Ray scaling نیستند. ۷ دامی cohort در سطح وارد شدند؛ reference cohort=۱۳۹۲–۱۳۹۴. urban/region mean دوباره اضافه نشدند. تحصیلات استفاده نشده است. منشأ قیمت و mapping در [گزارش cohort](../cohort/report.md) موجود است؛ قیمت دوباره ساخته نشد.''')
    add('diagnostics استنباط', table(['نام','مقدار'], [[k,v] for k,v in r['inference_diagnostics'].items() if not isinstance(v,(list,dict))]))
    di = r['inference_diagnostics']
    if 'same_fit_conditional_slope_wald' in di:
        old = di['same_fit_conditional_slope_wald']
        add('آیا تصحیح خطای استاندارد نتیجه را عوض کرد؟',
            f"در **همان مدل دو دوره‌ای و همان ضرایب**، میانهٔ نسبت SE کامل‌تر به SE conditional قدیمی {di['corrected_to_conditional_se_ratio_median']:.3f} و بیشترین نسبت {di['corrected_to_conditional_se_ratio_max']:.3f} است. آزمون سراسری از Wald={old['statistic']:.3f} با روش conditional به {main_test['statistic']:.3f} با روش چندمرحله‌ای می‌رسد. پس لحاظ مراحل قبلی و Jacobian/Sigma اهمیت عددی دارد، اما فرض برابری همچنان رد می‌شود. افزایش میانهٔ SE را نمی‌توان به همهٔ ضرایب به‌صورت یکسان نسبت داد.\n")
    co = r['shared_coefficients']
    add('تمام پارامترهای سطحی مشترک مدل اصلی', table(['گروه','alpha مرکز','delta S&Y','CF جاری kappa'],
        [[f'G{i+1}',co['alpha_at_center'][i],co['delta'][i],co['cf_current'][i]] for i in range(12)]))
    add('تمام ضرایب ترجمهٔ demographic/Mundlak/cohort در واحد اصلی', table(['نام']+[f'G{i+1}' for i in range(12)],
        [[name,*values] for name,values in zip(co['translation_names'],co['translations_original_units'])]))
    add('مرکز و مقیاس ترجمه‌ها', table(['نام','center','scale'],
        [[name,c,s] for name,c,s in zip(co['translation_names'],co['translation_centers'],co['translation_scales'])]))
    for item in r['coefficients_by_regime']:
        add('beta و lambda — '+item['label'], table(['گروه','beta','lambda'],
            [[f'G{i+1}',item['beta'][i],item['lambda'][i]] for i in range(12)]))
        add('ماتریس کامل gamma — '+item['label'], matrix(item['gamma']))
    add('اختلاف beta و lambda؛ بعد−قبل', table(['گروه','Delta beta','Delta lambda'],
        [[f'G{i+1}',r['parameter_differences']['beta'][i],r['parameter_differences']['lambda'][i]] for i in range(12)]))
    add('اختلاف کامل gamma؛ بعد−قبل', matrix(r['parameter_differences']['gamma'])+'\nاندازهٔ خام beta/gamma/lambda مستقیماً اندازهٔ اقتصادی پاسخ نیست؛ جدول کشش و شوک ۱۰٪ آن را قابل تفسیر می‌کند.\n')
    fn = free_names(co['translation_names'], ['beta','gamma','lambda'], r['labels'])
    assert len(fn) == len(r['free_coefficients'])
    add('تمام ۶۵۰ ضریب آزاد و خطای استاندارد اصلاح‌شدهٔ آنها', table(['پارامتر','ضریب','SE چندمرحله‌ای'],
        list(zip(fn,r['free_coefficients'],r['free_coefficient_standard_errors']))))
    add('تمام ضرایب مرحلهٔ مخارج', table(['نام','ضریب'], list(r['rf']['coefficients'].items())))
    add('تمام ضرایب ۱۲ Probit', table(['نام']+[f'G{i+1}' for i in range(12)],
        [[name,*row] for name,row in zip(r['probit_names'],np.asarray(r['probit_coefficients']).T)]))
    add('covariance خطای مدل اصلی', matrix(r['error_covariance']))
    add('قیود و سلامت پیش‌بینی مدل اصلی', table(['regime','sum alpha','sum beta','sum lambda','Gamma row max','Gamma symmetry max'],
        [[x[k] for k in ['label','alpha_sum','beta_sum','lambda_sum','gamma_row_sum_max','gamma_symmetry_max']] for x in r['restrictions']])+'\n'+
        table(['گروه','درصد fitted منفی','درصد fitted بالای یک'],
            [[f'G{i+1}',100*r['predictions']['negative_fraction'][i],100*r['predictions']['over_one_fraction'][i]] for i in range(12)])+
        f"\nRMSE مجموع fitted shares از یک={r['predictions']['fitted_adding_up_rmse']:.9g}. هیچ clipping اعمال نشده است.\n")
    for label, ee in r['elasticities_common_point'].items():
        add('تمام کشش‌های مخارج — '+label, table(['گروه','مخارج S&Y','مخارج نهفته'],
            [[f'G{i+1}',ee['expenditure'][i],ee['latent_expenditure'][i]] for i in range(12)]))
        for key in ['marshallian','hicksian_slutsky_convention','latent_marshallian']:
            add('ماتریس کامل '+key+' — '+label, matrix(ee[key]))
            if key != 'latent_marshallian': add('SE کامل '+key+' — '+label, matrix(r['elasticity_standard_errors'][label][key]))
    for key in ['marshallian','hicksian_slutsky_convention','latent_marshallian']:
        add('اختلاف کامل '+key+'؛ بعد−قبل', matrix(r['elasticity_differences'][key]))
        if key != 'latent_marshallian': add('SE اختلاف کامل '+key, matrix(r['elasticity_difference_standard_errors'][key]))

    if plain:
        add('نسخهٔ بدون S&Y و CF — دامنهٔ بررسی', '''این نسخه با دستور کاربر تخمین زده شد. همان نمونه، قیمت‌ها، cohortها و ۲۰ mean برون‌زا را دارد؛ CF جاری، mean CF و تمام مراحل Probit/S&Y حذف شدند. صفرهای خرید حفظ شدند. به علت جمع دقیق سهم مشاهده‌شده به یک، معادلهٔ دوازدهم در تخمین حذف و از قیود بازیابی می‌شود؛ کشش هر ۱۲ گروه گزارش می‌شود. Mundlak ترجمهٔ alpha همچنان وجود دارد؛ قید انحنا اضافه نشد.

برابری ضرایب با Wald خوشه‌ای خانوار و Jacobian مشاهده‌شده، همراه عدم‌اطمینان Sigma خود IFGNLS، بررسی می‌شود. حذف S&Y/CF نیاز به تصحیح مراحل تولیدشده را حذف می‌کند، ولی مسئلهٔ خرید صفر، درون‌زایی مخارج و مفروضات مشخصات را حل نمی‌کند؛ آزمون این نسخه نتیجهٔ خود این مدل ساده‌تر است.

روش‌های مناسبِ استخراج‌شده از ادبیات تکرار شدند: آزمون سراسری pooling/برابری، آزمون بلوک‌های قیمت و مخارج، مقایسهٔ بازه‌ها/cohortها، آزمون مقاوم restricted-score/LM و آزمون معادل‌بودن اقتصادی کشش‌ها. F معمول Chow برای رگرسیون خطی iid و LR معمول likelihood گاوسی iid برای این سیستم غیرخطی با خطای پنلی معتبر فرض نشدند؛ آزمون minimum-distance یک برآوردگر دیگر و آزمون تاریخ شکست نامعلوم نیز مکانیکی منتقل نشدند. «همهٔ آزمون‌های مناسب» به معنی اجرای آزمون‌های دارای مفروضات ناسازگار نیست.

آزمون score/LM می‌پرسد: وقتی مدل مشترک تخمین زده شده، آیا جهت‌های تغییر ضرایب هنوز اطلاعات توضیحی قابل تشخیصی دارند؟ برخلاف Wald که از مدل نامقید استفاده می‌کند، این آزمون در مدل مقید محاسبه می‌شود. اثر برآورد nuisance coefficients و Sigma از score حذف و سپس covariance خوشه‌ایِ باقی‌مانده حساب می‌شود؛ از LM سادهٔ iid استفاده نشده است. خانوادهٔ روش از Wooldridge (1990) می‌آید؛ نسخهٔ QUAIDS/خوشهٔ خانوار از معادلات همین برآوردگر مشتق و کنترل شده است.''')
        summaries = []
        for key in ['frame','temporal','cohort']:
            if key not in plain: continue
            model = plain[key]; test = model['tests']['all_selected_slopes_equal']
            summaries.append([key,test['statistic'],test['df'],ptext(test['pvalue']),model['convergence']['success']])
        add('نتیجهٔ آزمون‌های مدل ساده‌تر', table(['مقایسه','Wald','قیود','p','همگرایی'], summaries)+'\nسه بازه sensitivity به تجمیع زمانی است؛ مرز ۱۴۰۰ شکست اقتصادی کشف‌شده نیست. آزمون cohort فقط beta/lambda را متفاوت می‌کند و gamma مشترک است؛ آزمون کامل همگنی قیمت میان هشت cohort نیست.\n')
        score_rows = []
        for key in ['frame','temporal','cohort']:
            if key in plain and 'robust_restricted_score_equal' in plain[key]['tests']:
                t = plain[key]['tests']['robust_restricted_score_equal']
                score_rows.append([key,t['statistic'],t['df'],ptext(t['pvalue'])])
        if score_rows: add('آزمون تکمیلی score/LM در مدل ساده‌تر', table(['مقایسه','score/LM مقاوم','قیود','p'],score_rows))
        if 'frame' in plain:
            model = plain['frame']; labs = model['labels']
            add('مقایسهٔ مستقیم کشش‌های نسخهٔ ساده‌تر در دو دوره', table(
                ['گروه','مخارج قبل','مخارج بعد','قیمت خودی قبل','قیمت خودی بعد'],
                [[GROUPS[i],model['elasticities_common_point'][labs[0]]['expenditure'][i],
                  model['elasticities_common_point'][labs[1]]['expenditure'][i],
                  model['elasticities_common_point'][labs[0]]['marshallian'][i][i],
                  model['elasticities_common_point'][labs[1]]['marshallian'][i][i]] for i in range(12)]))
            comp = next(iter(model['economic_comparisons'].values()))
            add('اهمیت اقتصادی نسخهٔ ساده‌تر؛ دو دوره', table(['کشش','گروه','تفاوت','SE','p صفر Holm','پاسخ ۱۰٪؛ واحد درصد','اندازه با مرز ۰٫۱'],
                [[x['kind'],GROUPS[x['group']-1],x['difference_after_minus_before'],x['standard_error'],
                  ptext(x['pvalue_zero_holm_24']),x['quantity_response_gap_pp_for_10pct_shock'],economic_label(x)] for x in comp]))
            main0, main1 = [r['elasticities_common_point'][x] for x in r['labels']]
            simple0, simple1 = [model['elasticities_common_point'][x] for x in labs]
            add('کدام تفاوت‌ها در هر دو مدل دیده می‌شوند؟', table(
                ['گروه','Delta مخارج مدل اصلی','Delta مخارج ساده‌تر','Delta قیمت خودی مدل اصلی','Delta قیمت خودی ساده‌تر'],
                [[GROUPS[i],main1['expenditure'][i]-main0['expenditure'][i],
                  simple1['expenditure'][i]-simple0['expenditure'][i],
                  main1['marshallian'][i][i]-main0['marshallian'][i][i],
                  simple1['marshallian'][i][i]-simple0['marshallian'][i][i]] for i in range(12)])+'''
تغییر بزرگ حساسیت قیمت روغن در هر دو نسخه دیده می‌شود. ولی تغییر کشش قیمت برنج حتی جهت یکسان ندارد: در مدل اصلی حساسیت بیشتر و در مدل ساده‌تر کمتر شده است. بعضی تغییرات مخارج، مانند میوه، مغزها و نوشیدنی، هم با حذف S&Y/CF متفاوت‌اند. پس رد برابری در دو مدل پشتوانهٔ تکرار همان پرسش است، نه اثبات یکسان بودن اندازه و جهت همهٔ تغییرات. حذف CF با وجود آزمون معنی‌دار بودن آن در مدل اصلی، انتخاب مشخصات معتبرتر را خودکار تضمین نمی‌کند.
''')
        for kind in ['common','frame','temporal','cohort']:
            if kind not in plain: continue
            model = plain[kind]
            add('مدل ساده‌تر '+kind+' — همگرایی و استنباط', table(['diagnostic','value'],list(model['convergence'].items()))+'\n'+
                table(['inference','value'],list(model['inference_diagnostics'].items()))+'\n'+
                table(['H0','Wald','df','p'],[[k,v['statistic'],v['df'],ptext(v['pvalue'])] for k,v in model['tests'].items()]))
            add('مدل ساده‌تر '+kind+' — تمام ترجمه‌ها', table(['نام']+[f'G{i+1}' for i in range(12)],
                [[name,*row] for name,row in zip(model['translation_names'],model['translations_original_units'])]))
            for j, co in enumerate(model['coefficients_by_regime']):
                add('مدل ساده‌تر '+kind+' — alpha/beta/lambda '+co['label'], table(['گروه','alpha مرکز','beta','lambda'],
                    [[f'G{i+1}',co['alpha_at_center'][i],co['beta'][i],co['lambda'][i]] for i in range(12)]))
                if kind != 'cohort' or j == 0: add('مدل ساده‌تر '+kind+' — gamma '+co['label'], matrix(co['gamma']))
            fn = free_names(model['translation_names'], model['blocks_allowed_to_vary'], model['labels'], plain=True)
            assert len(fn) == len(model['free_coefficients'])
            add('مدل ساده‌تر '+kind+' — تمام ضرایب آزاد و SE', table(['نام','ضریب','SE'],
                list(zip(fn,model['free_coefficients'],model['free_standard_errors']))))
            sigma = model['error_covariance_11_equations']
            add('مدل ساده‌تر '+kind+' — covariance خطای ۱۱ معادله', table(['گروه']+[f'G{i+1}' for i in range(11)],
                [[f'G{i+1}',*row] for i,row in enumerate(sigma)]))
            labs = model['labels']
            add('مدل ساده‌تر '+kind+' — کشش مخارج تمام regimeها', table(['گروه']+labs,
                [[GROUPS[i],*[model['elasticities_common_point'][lab]['expenditure'][i] for lab in labs]] for i in range(12)]))
            add('مدل ساده‌تر '+kind+' — کشش خودی تمام regimeها', table(['گروه']+labs,
                [[GROUPS[i],*[model['elasticities_common_point'][lab]['marshallian'][i][i] for lab in labs]] for i in range(12)]))
            for lab, ee in model['elasticities_common_point'].items():
                for key in ['marshallian','hicksian_slutsky_convention']:
                    add('مدل ساده‌تر '+kind+' — ماتریس کامل '+key+' '+lab, matrix(ee[key]))
            add('مدل ساده‌تر '+kind+' — سلامت fitted shares', table(['گروه','درصد منفی','درصد بالای یک'],
                [[f'G{i+1}',100*model['predictions']['negative_fraction'][i],100*model['predictions']['over_one_fraction'][i]] for i in range(12)])+
                f"\nRMSE جمع سهم‌ها از یک={model['predictions']['fitted_adding_up_rmse']:.9g}.\n")
    add('ادبیات، کد و بازتولید', '''پشتوانهٔ انتخاب آزمون‌ها و تفکیک آزمون مناسب/نامناسب در [بررسی ادبیات](../preliminary_stability/literature_stability.md) آمده است؛ نمونهٔ Mussida–Sciulli پنل کوتاه با Mundlak و تعامل دوره را بررسی می‌کند. covariance جدید از این منابع استفاده می‌کند:

- Murphy, K. M. & Topel, R. H. (1985), *Estimation and Inference in Two-Step Econometric Models*, JBES 3(4):370–379. [اطلاعات مقاله](https://ideas.repec.org/a/bes/jnlbes/v3y1985i4p370-79.html).
- Hardin, J. W. (2002), *The robust variance estimator for two-stage models*, Stata Journal 2(3):253–266. [متن خوانده‌شده، به‌ویژه صفحات ۲۵۴–۲۵۵](https://www.stata-journal.com/sjpdf.html?articlenum=st0018).
- Wooldridge, J. M. (1990), *A Unified Approach to Robust, Regression-Based Specification Tests*, Econometric Theory 6(1):17–43. [ناشر](https://doi.org/10.1017/S0266466600004898)؛ [متن پیش‌نویس MIT WP 480، ژانویهٔ ۱۹۸۸، به‌ویژه Example 3.1/3.3](http://dspace.mit.edu/bitstream/handle/1721.1/64341/unifiedapproacht00wool.pdf;sequence=1). تاریخ آنلاین ۲۰۰۹ تاریخ انتشار اصلی مقاله نیست.

```bash
PILOT_BLAS_THREADS=3 python pilot/common/run.py --inputs intermediate/pilot_inputs --models CRE --no-year-season --cohort-instead-of-wave --stage-cache intermediate/pilot_inputs/frame_stage.pkl --cache-prefix cohort_ --output intermediate/pilot_inputs/frame_base.json
PILOT_BLAS_THREADS=3 python pilot/economic_stability/frame_stability.py --inputs intermediate/pilot_inputs
PILOT_BLAS_THREADS=3 python pilot/economic_stability/plain_stability.py --inputs intermediate/pilot_inputs
PILOT_BLAS_THREADS=3 python pilot/economic_stability/score_stability.py --inputs intermediate/pilot_inputs
python pilot/economic_stability/write_frame_report.py
OPENBLAS_NUM_THREADS=1 python -m unittest discover -s pilot/tests -p 'test_*.py'
```

هستهٔ pyquaidsce تغییر نکرد. source جدید لایهٔ regime، covariance و گزارش است. Jacobian تقاضا، Hessian واقعی score، حساسیت score به CDF/PDF و CF جاری/میانگین، cross-Jacobian Probit/مخارج و feedback مربوط به Sigma با تغییرات عددی مستقل بررسی شدند. نسخهٔ بدون S&Y/CF هم برای جمع سهم‌ها، قیود، Jacobian و Gram کنترل شد. derivative کشش با دو گام عددی مستقل بررسی شد. همهٔ cacheهای fitted object/covariance و دادهٔ فردی فقط در intermediate خصوصی‌اند.

نتایج کامل تجمیعی در [JSON مدل اصلی](results_frame_stability.json) و [JSON مدل ساده‌تر](results_plain_stability.json) هستند. گزارش‌های قبلی و مدل پایهٔ cohort تغییر نکرده‌اند.
'''+table(['ورودی','SHA256'],list(r['input_hashes'].items()))+
        '\nSample SHA256: `'+r['sample']['sample_hash']+'`. pyquaidsce commit: `'+r['pyquaidsce_commit']+'`.\n')
    (root/'report.md').write_text('\n'.join(parts).rstrip()+'\n')


if __name__ == '__main__': main()
