"""All stability tests, parameters and full elasticity matrices, in one report."""
# Support both direct scripts and python -m from the repository root.
if __package__ in (None, ""):
    import sys
    from pathlib import Path as _Path
    sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))

import json
from pathlib import Path
import numpy as np
from pilot.initial.write_report import table,matrix,GROUPS

p=Path(__file__).parent
r=json.loads((p/'results.json').read_text())
parts=['# آزمون‌های مقدماتی پایداری زمانی و تفاوت cohort در Mundlak/S&Y\n']
def add(title,body):parts.append('## '+title+'\n\n'+body+'\n')

def ptext(v):
    return '<1e-300' if v==0 else f'{v:.5g}'

summary=[]
for name in ['temporal','cohort']:
    if name not in r:continue
    m=r[name];w=m['tests']['all_selected_slopes_equal']
    desc='برابری زمانی gamma/beta/lambda' if name=='temporal' else 'برابری beta/lambda بین cohortها با gamma مشترک'
    summary.append([desc,w['statistic'],w['df'],ptext(w['pvalue']),m['convergence']['success']])
add('خلاصه اجرایی',f"نمونه ثابت: {r['sample']['estimation_panels']:,} خانوار و {r['sample']['estimation_rows']:,} مشاهده. همان ۱۰۶ کالا، ۱۲ گروه، قیمت‌های All و مدل حاشیه‌ای Mundlak/S&Y به کار رفتند. هفت cohort باقی‌اند؛ year، season و wave dummy وجود ندارد. دامی محدود دورهٔ ۱۴۰۰ به بعد در هر سه مرحله و در مدل‌های مقید و نامقید یکسان اضافه شد. تحصیلات، قید انحنا و bootstrap استفاده نشدند.\n\n"+table(['فرض صفر','Wald','df','p','converged'],summary)+'\nاین p-valueها conditional هستند: خوشه‌بندی panel_id هر سه موج را کنار هم نگه می‌دارد، ولی CF و Probitهای تخمینی ثابت گرفته شده‌اند. بنابراین نتایج پایلوت‌اند و جای استنباط نهایی با بازبرآورد مراحل را نمی‌گیرند. اختلاف عددی پارامترها خودِ معنی‌داری نیست؛ معنی‌داری آماری نیز خودِ اهمیت اقتصادی نیست.\n')
add('پشتوانهٔ ادبیات و جایگاه نتیجه', 'این اجرا از خانوادهٔ شناخته‌شدهٔ Wald coefficient-equality با تعامل دوره/گروه است. کاربرد پنل کوتاه + Mundlak در Mussida و Sciulli (2022)، آزمون pooling پنل‌های SIPP و قیود زمانیِ minimum-distance در پیش‌نویس Meyerhoefer و همکاران بررسی شدند. تطبیق دقیق، منابع و تفاوت نوع قیود در [گزارش ادبیات](literature_stability.md) آمده است. تقسیم ۱۴۰۰ تاریخ شکست کشف‌شده یا مرز اقتصادی تأییدشده نیست؛ این اجرا sensitivity به تجمیع زمانی است. p-valueها تا اصلاح uncertainty مراحل، conditional و مقدماتی‌اند.\n')
add('طراحی آزمون و محدودیت شناسایی', '''آزمون اصلی سه بازه دارد: ۱۳۹۲–۱۳۹۶، ۱۳۹۷–۱۳۹۹، ۱۴۰۰–۱۴۰۳. مرز ۱۳۹۷ تغییر مستند frame است، نه ادعای شکست اقتصادی. مرز ۱۴۰۰ یک تقسیم از پیش تعیین‌شده و محدود برای دورهٔ جدید است؛ تاریخ شکست از داده برآورد نشده است. تعداد پارامترها اجازه نمی‌دهد این پایلوت را آزمون برابری جداگانهٔ تمام ۱۲ سال بنامیم.

در مدل نامقید زمانی، هر gamma متقارن و homogeneous است؛ beta و lambda در هر بازه sum-to-zero دارند. هر بازه ۶۶ gamma و ۱۱ beta و ۱۱ lambda آزاد دارد؛ نسبت به مدل مقید ۱۷۶ پارامتر اضافه می‌شود. ضرایب demographic/Mundlak/cohort translations، CF، S&Y delta و covariance میان بازه‌ها مشترک‌اند. پس این یک آزمون محدود پایداری **پارامترهای اصلی تقاضا** است؛ ثبات همهٔ nuisance coefficients را آزمایش نمی‌کند.

آزمون تکمیلی هشت cohort فقط beta/lambda را آزاد می‌کند (۱۵۴ پارامتر اضافه)، با gamma مشترک. این آزمون تفاوت بلوک مخارج است و **آزمون جامع تفاوت ضرایب قیمت gamma بین cohortها نیست**. تفاوت cohort می‌تواند به زمان، ترکیب خانوار و frame نیز مربوط باشد؛ تفسیر آن یک اثر علّی خالص ورود نیست.

اثر سطحی pre/post۱۳۹۷ با cohortها هم‌خط است و دوباره اضافه نمی‌شود. اثر سطحی ۱۴۰۰ به بعد داخل RF، Probit و translated alpha در هر دو مدل مقید و نامقید وجود دارد؛ mean این دامی فقط تابع cohort است و اضافه کردن آن با cohortها هم‌خط می‌شود. RF و هر ۱۲ Probit برای این طراحی تازه برآورد شدند و سپس میان مدل‌های مقید/نامقید یکسان نگه داشته شدند. این مقایسه با تغییر نمونه یا قیمت مخلوط نشده است.

کشش‌های مقایسه‌ای در **یک نقطه مرجع مشترک** از کل نمونه محاسبه می‌شوند؛ قیمت، مخارج، سهم‌ها، CDF/PDF، CF و همهٔ mean/کنترل‌ها ثابت‌اند و فقط پارامترهای regime عوض می‌شوند. بنابراین اختلاف این کشش‌ها تغییر ترکیب نمونه یا قیمت میان دوره‌ها را منعکس نمی‌کند. این اعداد متوسط واقعی کشش خانوارهای هر دوره نیستند.

عدم رد فرض صفر اثبات برابری نیست؛ رد فرض صفر شواهد علیه مدل مقید، مشروط به مشخصات این پایلوت، است. مقایسه‌های بلوکی و جفتی تکمیلی‌اند و اصلاح چندآزمونی روی آن‌ها اعمال نشده است؛ آزمون زمانی سراسری معیار اصلی است.
''')
add('معادله',f'''a0={r['a0']:.12g} ثابت است؛ R کد دوره یا cohort است:

```text
a_i(Z) = alpha_i + Z theta_i
ln A_R = a0 + sum_i a_i(Z) ln p_i + 0.5 ln(p)' Gamma_R ln(p)
D_R = ln(x) - ln A_R
f_iR = a_i(Z) + Gamma_iR ln(p) + beta_iR D_R
       + lambda_iR exp(-beta_R' ln(p)) D_R^2
E[w_i | .] = Phi(k_i) [f_iR + kappa_i vhat] + delta_i phi(k_i)
```

H0 زمانی: Gamma_0=Gamma_1=Gamma_2، beta_0=beta_1=beta_2، lambda_0=lambda_1=lambda_2.
H0 cohort تکمیلی: beta و lambda برای تمام هشت cohort برابرند، با Gamma مشترک.
''')
add('نمونه و گروه‌ها',table(['گروه','نام'],[[f'G{i+1}',g] for i,g in enumerate(GROUPS)])+'\n'+table(['شرط sample flow','حذف جدید','باقی‌مانده'],[[x['criterion'],x['new_excluded_rows'],x['remaining_rows']] for x in r['sample']['flow']])+'\n'+table(['cohort سه‌ساله','خانوار'],[[f'{c}–{int(c)+2}',n] for c,n in r['sample']['cohort_counts'].items()]))
null=r['restricted_common_slopes']
add('مدل مقید و مراحل مشترک',table(['نام','مقدار'],list(null['convergence'].items()))+'\n'+table(['تنظیم','مقدار'],list(null['numerical_settings'].items()))+'\n'+table(['متغیر جاری'],[[n] for n in r['design']['level_controls']])+'\n'+table(['Mundlak mean'],[[n] for n in r['design']['Mundlak_variables']])+f"\nDesign columns={r['design']['columns']}, rank={r['design']['rank']}, condition={r['design']['condition']:.6g}. سالانه survey weight در RF و ساخت قیمت/Young استفاده می‌شود؛ Probit و IFGNLS همان قرارداد بدون وزن پایلوت قبلی را دارند.\n")
add('تمام ضرایب RF مشترک',table(['نام','ضریب'],list(null['first_stage']['coefficients'].items()))+'\n'+table(['diagnostic','مقدار'],[[k,v] for k,v in null['first_stage'].items() if not isinstance(v,dict)])+'\n'+table(['ابزارهای جاری درآمد','Wald','df','p'],[['cluster',[null['first_stage']['excluded_panel_cluster_wald']['statistic']][0],null['first_stage']['excluded_panel_cluster_wald']['df'],ptext(null['first_stage']['excluded_panel_cluster_wald']['pvalue'])]]))
add('تمام ضرایب Probit مشترک',table(['نام']+[f'G{i}' for i in range(1,13)],[[n,*row] for n,row in zip(null['probit_regressor_names'],np.array(null['probit_coefficients']).T)])+'\n'+table(['گروه','converged','iterations','purchase rate','Phi min','Phi max'],[[x['group'],x['converged'],x['iterations'],x['participation_rate'],x['Phi_min'],x['Phi_max']] for x in null['participation']]))

def parameter_tables(title,co,include_gamma=True):
    add(title+' — تمام ضرایب مشترک',table(['گروه','alpha centered','beta مرجع','lambda مرجع','delta','CF kappa'],[[f'G{i+1}',*[co[k][i] for k in ['alpha_at_center','beta','lambda','delta','cf_current']]] for i in range(12)]))
    if include_gamma:add(title+' — gamma مرجع',matrix(co['gamma']))
    add(title+' — تمام shifterها در واحد اصلی',table(['نام']+[f'G{i}' for i in range(1,13)],[[n,*row] for n,row in zip(co['translation_names'],co['translations_original_units'])]))
    add(title+' — مراکز و مقیاس‌ها',table(['نام','center','scale'],[[n,c,s] for n,c,s in zip(co['translation_names'],co['translation_centers'],co['translation_scales'])])+'\nضرایب استاندارد نیز در JSON موجودند. پارامترهای Ray rho/eta صفرند.\n')

parameter_tables('مدل مقید',null['coefficients'])
add('covariance مدل مقید',matrix(null['error_covariance']))
add('کشش مخارج مدل مقید',table(['گروه','کشش'],[[f'G{i+1}',v] for i,v in enumerate(null['elasticities']['expenditure'])]))
for key in ['marshallian','hicksian_slutsky_convention','latent_marshallian']:
    add('ماتریس کامل مدل مقید '+key,matrix(null['elasticities'][key]))

for name in ['temporal','cohort']:
    if name not in r:continue
    m=r[name];title='زمانی' if name=='temporal' else 'cohort تکمیلی'
    add('آزمون '+title,table(['H0','Wald','df مؤثر','قیود اسمی','p'],[[k,v['statistic'],v['df'],v['nominal_restrictions'],ptext(v['pvalue'])] for k,v in m['tests'].items()])+'\n'+table(['بازه','مشاهده'],list(m['counts'].items()))+'\n'+table(['diagnostic','value'],list(m['convergence'].items()))+f"\nFree parameters={m['free_parameters']}; additional={m['extra_parameters']}; runtime={m['wall_seconds']/60:.3f} min; final scaled GN ratio={m['inference_diagnostics']['gradient_scaled_gn_ratio']:.4e}.\n")
    add(title+' — قیود هر regime',table(['regime','sum alpha','sum beta','sum lambda','Gamma row max','Gamma symmetry max','sum CF','translation sum max'],[[x[k] for k in ['label','alpha_sum','beta_sum','lambda_sum','gamma_row_sum_max','gamma_symmetry_max','cf_sum','translation_sum_max']] for x in m['restrictions']]))
    parameter_tables(title,m['shared_coefficients'],include_gamma=name=='cohort')
    add(title+' — covariance',matrix(m['error_covariance']))
    for x in m['coefficients_by_regime']:
        add(title+' — beta/lambda '+x['label'],table(['گروه','beta','lambda'],[[f'G{i+1}',x['beta'][i],x['lambda'][i]] for i in range(12)]))
        if name=='temporal':add('gamma '+x['label'],matrix(x['gamma']))
    labels=m['labels']
    add(title+' — کشش مخارج در نقطه مشترک',table(['گروه']+labels,[[GROUPS[i],*[m['elasticities_common_point'][label]['expenditure'][i] for label in labels]] for i in range(12)]))
    add(title+' — own Marshallian در نقطه مشترک',table(['گروه']+labels,[[GROUPS[i],*[m['elasticities_common_point'][label]['marshallian'][i][i] for label in labels]] for i in range(12)]))
    for label,e in m['elasticities_common_point'].items():
        for key in ['marshallian','hicksian_slutsky_convention','latent_marshallian']:
            add(title+' — ماتریس کامل '+key+' '+label,matrix(e[key]))
        add(title+' — latent expenditure '+label,table(['گروه','کشش'],[[f'G{i+1}',v] for i,v in enumerate(e['latent_expenditure'])]))
    add(title+' — سلامت پیش‌بینی',table(['گروه','negative fitted fraction','above one fraction'],[[f'G{i+1}',m['predictions']['negative_fraction'][i],m['predictions']['over_one_fraction'][i]] for i in range(12)])+f"\nObserved fitted-share adding-up RMSE={m['predictions']['fitted_adding_up_rmse']:.8f}. raw S&Y دقیقاً adding-up مشاهده‌شده ندارد؛ هیچ clipping اعمال نشده است.\n")

add('بازتولید و منشأ', '''```bash
PILOT_BLAS_THREADS=3 python pilot/common/run.py --inputs intermediate/pilot_inputs --models CRE --no-year-season --cohort-instead-of-wave --late-period-control --stage-cache intermediate/pilot_inputs/stability_stage.pkl --cache-prefix stability_null_ --warm-start pilot/cohort/results.json --output intermediate/pilot_inputs/stability_null.json
PILOT_BLAS_THREADS=3 python pilot/preliminary_stability/stability.py --inputs intermediate/pilot_inputs
python pilot/preliminary_stability/write_stability_report.py
python -m unittest discover -s pilot/tests -p 'test_*core.py'
```

هسته pyquaidsce تغییر نکرده است؛ RegimeCore لایهٔ نازک روی PanelCore است. نسخهٔ صفرِ contrastها باید پیش‌بینی مدل مقید را دقیقاً بازتولید کند؛ قیود تمام regimeها و Jacobian مستقل با finite differences و structured Gram با نسخهٔ dense بررسی شده‌اند. آزمون‌های سابق هسته هم حفظ شدند.

''' +table(['input','SHA256'],list(r['input_hashes'].items()))+'\nSample SHA256: `'+r['sample']['sample_hash']+'`. pyquaidsce commit: `'+r['pyquaidsce_commit']+'`. جدول‌های قیمت و sample اصلی در [گزارش cohort](../cohort/report.md) و JSON این آزمون موجودند. هیچ household record در خروجی عمومی یا commit قرار نمی‌گیرد.\n')
(p/'report.md').write_text('\n'.join(parts))
