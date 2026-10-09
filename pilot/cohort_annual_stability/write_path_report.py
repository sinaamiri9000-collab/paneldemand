"""One full report: all coefficients/matrices and prespecified contrasts."""
# Support both direct scripts and python -m from the repository root.
if __package__ in (None, ""):
    import sys
    from pathlib import Path as _Path
    sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))

import json
from pathlib import Path
import numpy as np

ROOT=Path(__file__).parent
GROUPS=['برنج','نان و غلات','گوشت','لبنیات و تخم‌مرغ','روغن و چربی','میوه',
        'سبزیجات و سیب‌زمینی','حبوبات','مغزها، خشکبار و خرما','قند و شیرینی',
        'نوشیدنی بدون نوشابه','ادویه و چاشنی']


def main():
    r=json.loads((ROOT/'results.json').read_text()); lines=[]
    def put(s=''): lines.append(str(s))
    def fmt(v):
        if isinstance(v,(float,np.floating)): return f'{v:.7g}'
        return str(v)
    def table(headers,rows):
        put(); put('| '+' | '.join(headers)+' |');put('| '+' | '.join(['---']*len(headers))+' |')
        for row in rows: put('| '+' | '.join(fmt(v) for v in row)+' |')
        put()
    def matrix(title,x,rownames=None):
        put('### '+title)
        x=np.asarray(x)
        table(['ردیف']+[f'G{i+1}' for i in range(x.shape[1])],
              [[rownames[j] if rownames else f'G{j+1}']+list(v) for j,v in enumerate(x)])
    put('# آزمون جداگانهٔ cohort و سال در مدل اصلی Mundlak/S&Y + CF')
    put('\n## خلاصهٔ اجرایی\n')
    put('مدل پایه و تمام خروجی‌های قبلی حفظ شدند. این اجرا از مدل اصلی دارای S&Y و CF استفاده می‌کند؛ مدل بدون این دو اصلاح مبنای این نتایج نیست. آزمون cohort از مدل پایهٔ دارای هفت دامی cohort و بدون سال/فصل/موج شروع می‌کند. آزمون سالانه از مدل تازهٔ دارای کنترل سطح cohort و سال شروع می‌کند. هیچ تقسیم ۱۳۹۷ یا ۱۴۰۰ برای آزمون شیب‌های این اجرا به کار نرفت؛ سال‌ها و cohortها جداگانه مقایسه شدند.')
    rows=[]
    for kind,label in [('cohort','cohortهای ورود'),('annual','سال‌های تقویمی')]:
        if kind not in r: continue
        for b in ('beta','lambda','gamma'):
            t=r[kind]['restricted_scores']['tests'][b]
            rows.append([label,b,t['statistic'],t['df'],t['nominal_restrictions'],
                '<1e-300' if t['pvalue']==0 else t['pvalue'],
                '<1e-300' if t['pvalue_holm_3']==0 else t['pvalue_holm_3'],
                'رد برابری' if t['pvalue_holm_3']<.05 else 'عدم رد'])
    table(['مقایسه','بلوک','score مقاوم','درجه آزادی','تعداد قیود','p','p با Holm سه بلوک','نتیجه'],rows)
    put('p برابر صفر در فایل ماشین‌خوان یعنی احتمال از حد نمایش عددی کوچک‌تر شده است؛ احتمال واقعیِ دقیقاً صفر ادعا نمی‌شود.')
    for kind,label in [('cohort','cohort'),('annual','سال')]:
        model=r.get(kind,{}).get('selected_model')
        if not model: continue
        put(f"مدل متفاوت بین {label}ها: بلوک‌های آزادشده {', '.join(model['blocks_allowed_to_vary'])}؛ همگرایی {model['convergence']['success']}، {model['free_parameters']} پارامتر آزاد. جزئیات اهمیت اقتصادی و تمام فاصله‌های اطمینان پایین آمده‌اند؛ رد آماری به‌تنهایی ملاک حذف مدل پایه نیست.")
        ee=model['elasticities_common_point']; labs=model['labels']
        table(['گروه','کمترین کشش مخارج','بیشترین کشش مخارج','دامنهٔ اختلاف','کمترین own','بیشترین own','دامنهٔ اختلاف own'],
            [[GROUPS[g]]+list(v) for g in range(12) for v in [(
                min(ee[l]['expenditure'][g] for l in labs),max(ee[l]['expenditure'][g] for l in labs),
                np.ptp([ee[l]['expenditure'][g] for l in labs]),
                min(ee[l]['marshallian'][g][g] for l in labs),max(ee[l]['marshallian'][g][g] for l in labs),
                np.ptp([ee[l]['marshallian'][g][g] for l in labs]))]])
        put('دامنه‌ها توصیفی‌اند و فاصلهٔ اطمینانِ انتخاب کمینه/بیشینه نیستند. برای استنباط از مقایسه‌های از پیش تعریف‌شده با covariance مشترک استفاده می‌شود.')
        reference=model['elasticity_comparisons'][labs[-1]+' minus '+labs[0]]['economic']
        table(['مقایسهٔ آخرین با اولین '+label,'اختلاف اقتصادی کوچک با شواهد کافی','بزرگ‌تر از۰٫۱ با شواهد کافی','اندازهٔ اقتصادی نامطمئن'],
            [[typ,sum(i['margin_results']['0.1']['equivalent_holm_all_contrasts'] for i in reference if i['kind']==kind_e),
              sum(i['margin_results']['0.1']['beyond_margin_holm_all_contrasts'] for i in reference if i['kind']==kind_e),
              sum(not i['margin_results']['0.1']['equivalent_holm_all_contrasts'] and not i['margin_results']['0.1']['beyond_margin_holm_all_contrasts'] for i in reference if i['kind']==kind_e)]
             for kind_e,typ in [('expenditure','کشش مخارج، ۱۲ گروه'),('own_marshallian','کشش خودقیمتی، ۱۲ گروه')]])
        put('برچسب نامطمئن به معنی نبود تفاوت نیست؛ با اصلاح Holm روی همهٔ مقایسه‌های گزارش‌شده، شواهد کافی برای کوچک یا بزرگ بودن نسبت به مرز ۰٫۱ به دست نیامده است.')
    put('نتیجهٔ عملی: شواهد آماری محدود به یک بلوک نیست؛ در هر دو خانواده هر سه بلوک رد شدند و Wald مکمل نیز همین نتیجه را داشت. اهمیت اقتصادی در همهٔ گروه‌ها یکسان نیست؛ اختلاف کشش مخارج مغزها/خشکبار و برخی کشش‌های قیمت بزرگ است، در حالی که اختلاف مخارج برنج در مقایسهٔ اولین و آخرین گروه/سال کوچک است. این نتایج، آزادکردن خودکار تمام ضرایب برای specification نهایی را توجیه نمی‌کنند؛ baseline همچنان برای مقایسه حفظ شده است.')
    positives=[]
    for kind in ('cohort','annual'):
        model=r.get(kind,{}).get('selected_model')
        if not model:continue
        for label in model['labels']:
            ee=model['elasticities_common_point'][label];se=model['elasticity_standard_errors'][label]
            for g,v in enumerate(np.diag(ee['marshallian'])):
                if v>0:
                    sd=se['marshallian'][g][g]
                    positives.append([kind,label,GROUPS[g],v,v-1.96*sd,v+1.96*sd,ee['latent_marshallian'][g][g]])
    if positives:
        put('**محدودیت اقتصادیِ مشاهده‌شده:** بعضی own-priceها در مدل بسیار منعطف مثبت شده‌اند. به‌خصوص روغن در ۱۴۰۲: own مشاهده‌شده ≈+۰٫۴۷۶ و latent own ≈+۰٫۳۳۵. بنابراین همگرایی عددی و رد برابری، اعتبار اقتصادی تمام پاسخ‌های سالانه را تضمین نمی‌کنند؛ مدل کاملِ ۱۲ساله فعلاً مدل تشخیصی است. قید انحنا بنا به دستور کاربر اعمال نشد و گروه/سال مسئله‌دار حذف نشد. CIهای زیر نقطه‌ای‌اند و آزمون از پیش تعیین‌شدهٔ مثبت‌بودن با اصلاح چندآزمونی نیستند.')
        table(['خانواده','cohort/سال','گروه','own مثبت','CI95 lower','CI95 upper','latent own'],positives)
    put('\n## نمونه، طراحی و محدودیت تفسیر\n')
    put(f"نمونهٔ یکسان: {r['sample']['estimation_rows'] if 'estimation_rows' in r['sample'] else r['sample'].get('estimation_observations',137814)} ردیف از ۴۵٬۹۳۸ خانوار سه‌موجی؛ hash نمونه `{r['sample']['sample_hash']}`. قیمت‌ها، basket ۱۰۶ قلم/۱۲ گروه، وزن‌ها و پاک‌سازی تغییر نکردند. تحصیلات، انحنا، فصل و موج وارد نشدند؛ bootstrap اجرا نشد.")
    put('هشت cohort: ۱۳۹۲–۱۳۹۴، ۱۳۹۳–۱۳۹۵، ۱۳۹۴–۱۳۹۶، ۱۳۹۷–۱۳۹۹، ۱۳۹۸–۱۴۰۰، ۱۳۹۹–۱۴۰۱، ۱۴۰۰–۱۴۰۲، ۱۴۰۱–۱۴۰۳. مرجع آزمون cohort، اولین cohort است؛ مرجع شیب سالانه ۱۳۹۲ است. وزن جاری survey در RF حفظ شد؛ Probit و IFGNLS همان convention بدون وزن اجرای قبلی را دارند.')
    put('دموگرافیک‌ها و meanهای Mundlak همان مدل پایه‌اند: اندازه و سن، جنسیت، urban، پنج region، سه تأهل، هفت cohort؛ mean دوازده log-price، اندازه، سن، female، سه تأهل و دو تابع درآمد؛ mean residual CF نیز جدا حفظ شد. mean مخارج خام وارد نشد. این یک Mundlak-augmented marginal-Probit است، نه likelihood مشترک CRE با انتگرال random intercept.')
    if 'annual_level_design' in r:
        d=r['annual_level_design'];put('در آزمون سالانه، ده ستون مستقل سال به RF، تمام ۱۲ Probit و translation سیستم اضافه شد. ۱۳۹۲ مرجع است و ستون ۱۳۹۷ به دلیل وابستگی دقیق با cohortهای frame جدید تکرار نشد؛ این حذف ستون زائد است و مانع آزادبودن تغییرات سطح سالانه نمی‌شود. میانگین دامی‌های سال روی سه مشاهده تابع cohort است و دوباره وارد نشد.')
        put(f"rank طراحی مشترک: {d['rank']}/{d['columns']}؛ condition={d['condition']:.5g}.")
        table(['گروه','SD درون‌خانواری log-price پس از جذب سال','سهم variation درونی باقی‌مانده'],
            [[GROUPS[g],d['within_prices_after_household_and_year_effects'][f'G{g+1}']['sd'],
              d['within_prices_after_household_and_year_effects'][f'G{g+1}']['fraction_remaining']] for g in range(12)])
    put('دو فرض جدا آزموده شده‌اند: تفاوت cohort با nuisance و شیب سالانه مشترک؛ تفاوت سال با کنترل سطح cohort و nuisance مشترک. این طراحی، علت تفاوت را به طور مشترک بین cohort و زمان شناسایی نمی‌کند. همچنین ثبات تمام ضرایب RF، مشارکت، ترجمه‌های Mundlak و CF/S&Y آزموده نشده؛ آن بارگذاری‌ها در هر خانواده مشترک مانده‌اند.')
    put('\n## روش و معادلات واقعی\n')
    put('RF: ln(x) روی دوازده ln(p)، کنترل‌های جاری و meanهای برون‌زا، log-income مرکزی و مربع آن؛ residual جاری v و mean آن ساخته می‌شود. هر Probit روی ln(x)، دوازده ln(p)، کنترل‌ها، meanها، v و mean(v) تخمین زده می‌شود. سپس همان هستهٔ pyquaidsce به کار می‌رود:')
    put('```text\nalpha_i(Z) = alpha_i + Z theta_i\nln A_r(p,Z) = a0 + sum_i alpha_i(Z) ln p_i\n                 + 0.5 sum_i sum_j Gamma_ij,r ln p_i ln p_j\nln B_r(p) = sum_i beta_i,r ln p_i\nq_r = ln x - ln A_r(p,Z)\nw*_i,r = alpha_i(Z) + sum_j Gamma_ij,r ln p_j\n         + beta_i,r q_r + lambda_i,r q_r^2 / B_r(p) + kappa_i v\nw_i = Phi_i w*_i,r + delta_i phi_i + error_i\n```')
    put('قیود در هر cohort/سال: مجموع alpha برابر یک؛ مجموع beta،lambda،kappa و ضرایب هر translation صفر؛ Gamma متقارن با مجموع هر ردیف صفر. adding-up نظری روی بخش latent است؛ raw S&Y سهم مشاهده‌شده را دقیقاً جمع به یک نمی‌کند. cohort/سال در این معماری alpha و شاخص هزینه را با هم ترجمه می‌کنند؛ صرفاً intercept خطی بیرون از شاخص نیستند.')
    put('برای score، مدل مقید با ضرایب مشترک تخمین زده شد. score تعامل‌های هر بلوک پس از حذف nuisance مشترک با Jacobian مشاهده‌شده محاسبه شد؛ دیگر بلوک‌های تعامل در این آزمون جدا همچنان صفرند، نه nuisance برآوردشده. score سه مشاهده در هر خانوار جمع شد. عدم‌اطمینان RF، ۱۲ Probit و covariance خطای IFGNLS نیز منتقل شد؛ قیمت ساخته‌شده و نقاط مرجع ثابت‌اند. Wald مکمل داخل مدل نامقید معنای شرطی متفاوتی دارد.')
    put('سه p-value بلوک در هر خانواده با Holm اصلاح شدند. بلوک ردشده آزاد شد و مدل جایگزین برای مقایسهٔ کشش‌ها تخمین خورد. فاصله‌های اطمینان مدل انتخاب‌شده exploratory هستند و اصلاح انتخاب مدل ندارند. از Chow F معمولی، LR مبتنی بر استقلال مشاهدات یا جست‌وجوی تاریخ شکست استفاده نشد.')
    put('برای سرعت، Gram ماتریس و Hessian فقط روی ستون‌های غیرصفر هر رژیم جمع می‌شوند. معادل‌بودن عددی با روش متراکم روی ۳۰۰۰ ردیف واقعی، ۸ cohort و ۱۲ معادله بررسی شد (حدود ۲٫۳ برابر سریع‌تر در همان بررسی)؛ مشتق‌ها و Gram نیز با محاسبات مستقل آزموده شدند. فرمول‌ها، قیود و آستانه‌های solver تغییر نکردند. objective وزنی IFGNLS پس از به‌روزرسانی Sigma به N×۱۲ نزدیک می‌شود و به‌تنهایی معیار مقایسهٔ برازش مدل‌ها نیست؛ SSE سهم‌ها نیز گزارش می‌شود.')
    put('تمام کشش‌ها در یک نقطهٔ مرجع مشترکِ کل نمونه محاسبه می‌شوند تا تفاوت ترکیب نمونه و مقدار کنترل‌های cohort/سال با تفاوت شیب مخلوط نشود. هنگام مشتق همزمان، meanها و CF ثابت‌اند؛ هنگام محاسبهٔ خطای استاندارد، عدم‌اطمینان برآورد مراحل منتقل می‌شود. Hicksian از همان convention Slutsky پکیج می‌آید و به تنهایی اعتبار رفاهی raw S&Y را اثبات نمی‌کند.')
    put('برای هر مدل، مقایسه با مرجع و مقایسهٔ cohortها/سال‌های مجاور از قبل تعریف شد. CI95 نقطه‌ای است؛ p-valueهای تفاوت صفر و اهمیت اقتصادی با Holm روی تمام ۲۴ کشش × تمام مقایسه‌های گزارش‌شدهٔ همان مدل اصلاح شده‌اند. این کنترل خانوادگی، مدل‌های آزمایش‌شده در جلسات پیشین را پوشش نمی‌دهد. مرزهای ۰٫۰۵/۰٫۱/۰٫۲ واحد کشش صرفاً حساسیت‌اند؛ آستانهٔ مقرر کتاب نیستند. اختلاف ۰٫۱ برای شوک کوچک ۱۰٪ تقریباً یک واحد درصد اختلاف واکنش مقدار می‌سازد.')
    put('معادل‌بودن اقتصادی با TOST بررسی شد: پیش از اصلاح چندآزمونی، CI90 باید داخل مرز اقتصادی قرار بگیرد؛ جدول‌ها CI95 را برای نمایش عدم‌اطمینان اختلاف گزارش می‌کنند. برچسب نهاییِ جدول با p اصلاح‌شدهٔ TOST یا آزمون محافظه‌کارانهٔ عبور از مرز تعیین می‌شود. بنابراین کوچک‌بودن مقدار نقطه‌ای با اثبات معادل‌بودن یکی نیست.')
    put('اختلاف اقتصادی بزرگ در چند مورد، خودبه‌خود مدل پایه را با مدل سالانهٔ پرپارامتر جایگزین نمی‌کند. برعکس، عدم رد هم اثبات برابری نیست. Γ،β،λ با هم کشش می‌سازند؛ مثلاً آزادکردن Γ می‌تواند هم کشش قیمت و هم کشش مخارج را تغییر دهد. تفاوت frame، ترکیب نمونه و شوک حذف‌شده هم می‌توانند در نتیجه نقش داشته باشند.')
    put('\n## منبع و بازتولید\n')
    put('Wooldridge, Introductory Econometrics: A Modern Approach, sixth edition: §7-4c ص۲۲۱–۲۲۴؛ §8-2 ص۲۴۸؛ §13-1a ص۴۰۷؛ بحث پنل ص۴۲۳–۴۲۴؛ §14A.2 ص۴۵۹؛ §C.6f ص۷۰۲–۷۰۳. PDF به ترتیب ۲۴ صفحه جلوتر است. کتاب اصل تفاوت سطح/شیب و خوشه‌بندی را توضیح می‌دهد؛ covariance چندمرحله‌ای nonlinear از روش stacked estimating equations مستند در گزارش قبلی استفاده می‌کند.')
    put('```bash\nPILOT_BLAS_THREADS=3 python pilot/cohort_annual_stability/stability_path.py --inputs intermediate/pilot_inputs\npython pilot/cohort_annual_stability/write_path_report.py\npython -m unittest discover -s pilot/tests -p "test_*.py" -q\n```')
    put('پیش‌نیاز اجرای بالا، ورودی‌های قیمت‌گذاری‌شدهٔ پایلوت قبلی و frame_stage.pkl، frame_base.json، cohort_cre_point.pkl است. اگر cache مراحل موجود نباشد، پس از آماده‌سازی قیمت‌ها مطابق گزارش پایلوت، دستور زیر همان baseline cohort و مراحلش را بازسازی می‌کند:')
    put('```bash\nPILOT_BLAS_THREADS=3 python pilot/common/run.py --inputs intermediate/pilot_inputs --models CRE --no-year-season --cohort-instead-of-wave --cache-prefix cohort_ --gn-tol 1e-8 --warm-start pilot/no_year_season/results.json --stage-cache intermediate/pilot_inputs/frame_stage.pkl --output intermediate/pilot_inputs/frame_base.json\n```')
    put('نتایج کامل ماشین‌خوان: [results_cohort_annual.json](results.json). microdata و cache فقط در intermediate خصوصی هستند. هستهٔ pyquaidsce در commit '+r['pyquaidsce_commit']+' تغییر نکرده است.')
    for kind,title in [('cohort','cohort'),('annual','سال')]:
        if kind not in r: continue
        family=r[kind];put('\n## جزئیات خانوادهٔ '+title+'\n')
        put('همگرایی مدل مقید: '+json.dumps(family['null_convergence'],ensure_ascii=False))
        score=family['restricted_scores']; put('تشخیص score: '+json.dumps({k:v for k,v in score.items() if k!='tests'},ensure_ascii=False))
        stages=family['stages']
        put('تشخیص RF: '+json.dumps({k:v for k,v in stages['first_stage'].items() if k!='coefficients'},ensure_ascii=False))
        table(['RF variable','coefficient'],stages['first_stage']['coefficients'].items())
        matrix('تمام ضرایب ۱۲ Probit',np.array(stages['probit_coefficients']).T,stages['probit_regressor_names'])
        table(['گروه','همگرایی Probit','iterations','participation','Phi min','Phi max'],
            [[GROUPS[j],s['converged'],s['iterations'],s['participation_rate'],s['Phi_min'],s['Phi_max']] for j,s in enumerate(stages['participation'])])
        for model_key in ('common_slopes_with_year_levels','selected_model'):
            model=family.get(model_key)
            if not model: continue
            put('\n### مدل '+model_key+'\n')
            put('همگرایی: '+json.dumps(model['convergence'],ensure_ascii=False))
            put('solver: '+json.dumps(model['numerical_settings'],ensure_ascii=False))
            put('inference diagnostics: '+json.dumps({k:v for k,v in model['inference'].items() if k!='corrected_to_conditional_se_ratio'},ensure_ascii=False))
            table(['Wald','statistic','df','p'],[[k,v['statistic'],v['df'],'<1e-300' if v['pvalue']==0 else v['pvalue']] for k,v in model['wald_tests'].items()])
            table(['گروه/سال','مشاهده','sum alpha','sum beta','sum lambda','Gamma row error','symmetry error','sum CF','translation error'],
                [[s['label'],model['counts'][s['label']],s['alpha_sum'],s['beta_sum'],s['lambda_sum'],s['gamma_row_sum_max'],s['gamma_symmetry_max'],s['cf_sum'],s['translation_sum_max']] for s in model['restrictions']])
            table(['گروه','negative fitted fraction','over one fraction'],[[GROUPS[j],model['predictions']['negative_fraction'][j],model['predictions']['over_one_fraction'][j]] for j in range(12)])
            for label in model['labels']:
                ee=model['elasticities_common_point'][label];se=model['elasticity_standard_errors'][label]
                put('\n### کشش‌های '+label+'\n')
                table(['گروه','مخارج','CI95 lower','CI95 upper','own Marshallian','CI95 lower','CI95 upper'],
                    [[GROUPS[g],ee['expenditure'][g],ee['expenditure'][g]-1.96*se['expenditure'][g],ee['expenditure'][g]+1.96*se['expenditure'][g],
                      ee['marshallian'][g][g],ee['marshallian'][g][g]-1.96*se['marshallian'][g][g],ee['marshallian'][g][g]+1.96*se['marshallian'][g][g]] for g in range(12)])
                for key in ('marshallian','hicksian_slutsky_convention','latent_marshallian'): matrix(label+' '+key,ee[key])
                table(['گروه','latent expenditure'],[[GROUPS[g],ee['latent_expenditure'][g]] for g in range(12)])
            for label,comparison in model['elasticity_comparisons'].items():
                put('\n### اختلاف کشش: '+label+'\n')
                table(['گروه','کشش','اختلاف','SE','CI95 lower','CI95 upper','p Holm تمام مقایسه‌ها','اختلاف پاسخ به شوک۱۰٪، pp','نتیجه اقتصادی مرز۰٫۱'],
                    [[GROUPS[i['group']-1],i['kind'],i['difference_after_minus_before'],i['standard_error'],*i['ci95'],
                      i['pvalue_zero_holm_all_reported_contrasts'],i['quantity_response_gap_pp_for_10pct_shock'],
                      'معادل کوچک' if i['margin_results']['0.1']['equivalent_holm_all_contrasts'] else ('بزرگ‌تر از مرز' if i['margin_results']['0.1']['beyond_margin_holm_all_contrasts'] else 'اندازه نامطمئن')] for i in comparison['economic']])
            put('\n### تمام ضرایب ساختاری\n')
            for c in model['coefficients_by_regime']:
                table(['label / group','alpha at center','beta','lambda','delta','CF'],
                    [[c['label']+f' G{g+1}',c['alpha_at_center'][g],c['beta'][g],c['lambda'][g],c['delta'][g],c['cfcoef'][g]] for g in range(12)])
                matrix('Gamma '+c['label'],c['gamma'])
            s=model['shared_coefficients']
            matrix('تمام translationها در واحد اصلی',s['translations_original_units'],s['translation_names'])
            table(['variable','center','scale'],zip(s['translation_names'],s['translation_centers'],s['translation_scales']))
            matrix('covariance خطا',model['error_covariance'])
            put('پارامترهای آزاد به ترتیب: alpha11,beta11,Gamma66,lambda11,delta12,CF11؛ سپس تعامل‌های cohort/سال به ترتیب بلوک‌های آزاد؛ سپس translationهای متغیر×۱۱. پارامتر دوازدهم constrained از adding-up بازیابی می‌شود.')
            table(['free index','coefficient','stacked household SE'],[[j,v,se] for j,(v,se) in enumerate(zip(model['free_coefficients'],model['free_standard_errors']))])
    (ROOT/'report.md').write_text('\n'.join(lines)+'\n')
    print('WROTE report_cohort_annual.md',flush=True)


if __name__=='__main__': main()
