"""Render all aggregate results and complete coefficient/elasticity tables."""
# Support both direct scripts and python -m from the repository root.
if __package__ in (None, ""):
    import sys
    from pathlib import Path as _Path
    sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))

import argparse,json
from pathlib import Path
import numpy as np

GROUPS=['برنج','نان، غلات، آرد و رشته','گوشت','لبنیات و تخم‌مرغ','روغن‌ها و چربی‌ها',
        'میوه','سبزیجات و سیب‌زمینی','حبوبات','مغزها، خشکبار و خرما','قند، شیرینی و تنقلات','نوشیدنی‌ها بدون نوشابه','ادویه و چاشنی‌ها']
START='<!-- numerical-results:start -->';END='<!-- numerical-results:end -->'

def fmt(x):
    if isinstance(x,str):return x.replace('|','\\|').replace('\n','<br>')
    if x is None:return '—'
    return f'{float(x):.9g}'

def table(head,rows):
    return '\n'.join(['| '+' | '.join(head)+' |','| '+' | '.join(['---']*len(head))+' |']+
      ['| '+' | '.join(fmt(x) for x in row)+' |' for row in rows])+'\n'

def matrix(M):
    return table(['گروه / ستون']+[f'G{i}' for i in range(1,13)],
                 [[f'G{i+1}',*row] for i,row in enumerate(M)])

def main():
    p=argparse.ArgumentParser();p.add_argument('--results',type=Path,default=Path(__file__).parent/'results.json')
    p.add_argument('--report',type=Path,default=Path(__file__).parent/'report.md');args=p.parse_args()
    r=json.loads(args.results.read_text());a,b=r['Pooled'],r['CRE']
    ap=np.diag(a['elasticities']['marshallian']);bp=np.diag(b['elasticities']['marshallian'])
    ae=np.array(a['elasticities']['expenditure']);be=np.array(b['elasticities']['expenditure'])
    de=100*np.mean(np.abs((be-ae)/ae));dp=100*np.mean(np.abs((bp-ap)/ap))
    summary=f'''پایلوت **از نظر عددی قابل اجراست**: هر دو سیستم روی همان ۴۵٬۹۳۸ خانوار / ۱۳۷٬۸۱۴ مشاهده Panel B همگرا شدند و هسته pyquaidsce بدون fork استفاده شد. مدل حاشیه‌ای Mundlak/S&Y در {b['convergence']['outer_iterations']} تکرار IFGNLS و {b['convergence']['gn_iterations']} گام GN همگرا شد؛ زمان اجرای مراحل آن حدود {r['runtime']['CRE_total_stage_wall_seconds']/60:.2f} دقیقه بود. این نتیجه full joint CRE random-effects estimator یا specification نهایی مقاله نیست.

کنترل‌های Mundlak در بلوک تقاضای نهفته به‌طور مشترک معنادارند: Wald={b['inference_diagnostics']['mundlak_joint_test']['statistic']:.2f}، df=220، p<1e-300، با sandwich خوشه‌ای خانوار و generated stages ثابت. در هر ۱۲ Probit نیز mean controls در سطح ۵٪ معنادارند؛ ضعیف‌ترین مورد سبزیجات با p≈0.0204 است. اینها آزمون‌های مقدماتی conditional هستند و تفسیر علی یا inference نهایی ندارند.

هر ۱۲ کشش قیمتی خودی در هر دو مدل منفی‌اند. میانگین قدرمطلق تغییر نسبی own-price elasticity حدود **{dp:.2f}٪** و برای expenditure elasticity حدود **{de:.2f}٪** است؛ تفاوت‌ها برای بعضی گروه‌ها بزرگ‌اند. برای نمونه، کشش خودی لبنیات از {ap[3]:.3f} به {bp[3]:.3f} و مغزها/خشکبار از {ap[8]:.3f} به {bp[8]:.3f} تغییر می‌کند. این تغییر به تغییر sample، سبد یا قیمت بین دو مدل مربوط نیست؛ CF، participation و mean controls هر مدل جداگانه تخمین زده شده‌اند.

هیچ group price مفقودی باقی نماند. national-season فقط ۰٫۸۱٪ item-price assignments Panel B را پوشش می‌دهد. تغییرات درون‌خانوار قیمت برای هر ۱۲ گروه مثبت است و پس از کنترل‌های زمانی نیز ماتریس قیمت رتبه کامل ۱۲ دارد. نان/غلات کمترین سهم within از total variance، حدود ۸٫۷٪، را دارد؛ این به‌تنهایی اثبات causal price identification نیست.

محدودیت‌های قابل مشاهده: raw SY fitted shares دقیقاً جمع یک ندارند، RMSE جمع سهم در Mundlak {b['predictions']['fitted_adding_up_rmse']:.6f} است؛ سهم fitted منفی در نان/غلات حدود {100*b['predictions']['negative_fitted_fraction'][1]:.3f}٪ ردیف‌هاست. SSE با Mundlak حدود {100*(1-b['convergence']['unweighted_share_sse']/a['convergence']['unweighted_share_sse']):.2f}٪ کمتر است، اما conditional log-likelihood پایین‌تر است. پس ادعای برتری یکنواخت برازش نمی‌کنیم. SY meanهای دو مدل به‌سبب RF/participation متفاوت، nested conditional models نیستند و LR test از اختلاف این log-likelihoodها استفاده نشده است. مسئله adding-up **conditional observed means** و استنباط generated stages برای نسخه نهایی باز است.

سبد تحلیل با دستور کاربر بدون نوشابه، ۱۰۶ قلم در ۱۲ گروه است. تحصیلات و قید انحنا استفاده نشده‌اند. bootstrap بزرگ اجرا نشده است.'''
    text=args.report.read_text()
    marker='نتایج عددی پس از پایان هر دو تخمین در این بخش ثبت می‌شوند.'
    if marker in text:text=text.replace(marker,summary)
    else:
        lo=text.index('## خلاصه اجرایی')+len('## خلاصه اجرایی')
        hi=text.index('## دامنه و تصمیم‌های داده',lo)
        text=text[:lo]+'\n\n'+summary+'\n\n'+text[hi:]
    sections=[]
    def add(title,body):sections.append(f'## {title}\n\n{body}\n')
    add('نتایج عددی و ترتیب گروه‌ها',table(['شناسه','گروه'],[[f'G{i+1}',n] for i,n in enumerate(GROUPS)])+
        '\nهمه جدول‌های زیر کامل‌اند. جهت ماتریس کشش `[گروه مصرف، قیمت گروه ستون]` است. اعداد با ۹ رقم معنادار نمایش داده می‌شوند؛ JSON precision کامل محاسبات را نگه می‌دارد. جدول‌های wide در GitHub قابل پیمایش افقی‌اند.\n')
    fields=[('IFGNLS iterations','convergence','outer_iterations'),('GN steps','convergence','gn_iterations'),
      ('objective','convergence','objective'),('conditional log likelihood','convergence','log_likelihood'),
      ('unweighted share SSE','convergence','unweighted_share_sse'),('sigma condition','convergence','sigma_condition'),
      ('scaled GN ratio','inference_diagnostics','gradient_scaled_gn_ratio'),('max scaled score','inference_diagnostics','max_scaled_score'),
      ('scaled information minimum eigenvalue','inference_diagnostics','information_scaled_min_eigenvalue'),
      ('scaled information condition','inference_diagnostics','information_scaled_condition'),
      ('observed share sum RMSE','predictions','fitted_adding_up_rmse')]
    add('همگرایی و سلامت عددی',table(['diagnostic','Pooled-B','Mundlak-B'],[[n,a[k][v],b[k][v]] for n,k,v in fields])+
        '\nsolver success و parameter finiteness برای هر دو true هستند. symmetry دقیق است و خطای قیود sum-to-zero کمتر از 1e-16 است. a0 مشترک برابر '+fmt(r['a0'])+' است. هر دو scaled GN ratio از 1e-12 کوچک‌ترند.\n'+
        table(['model','algorithm','GN tolerance','param tolerance','objective tolerance','outer tolerance'],
              [[t,*[r[t]['numerical_settings'][k] for k in ['algorithm','gn_tol','param_tol','objective_tol','outer_param_tol']]] for t in ['Pooled','CRE']]))
    add('مقایسه کشش مخارج و قیمتی خودی',table(['گروه','expenditure Pooled','expenditure Mundlak','own Marshallian Pooled','own Marshallian Mundlak','own Hicksian Pooled','own Hicksian Mundlak'],
        [[f'G{i+1}',ae[i],be[i],ap[i],bp[i],np.diag(a['elasticities']['hicksian_slutsky_convention'])[i],np.diag(b['elasticities']['hicksian_slutsky_convention'])[i]] for i in range(12)]))
    v=r['variation'];cv=r['conditional_within_prices']['prices']
    add('within و between variation',table(['متغیر','overall SD','between SD','within SD','within / total variance','within SD after time FE'],
        [[n,v[n]['overall_sd'],v[n]['between_sd'],v[n]['within_sd'],v[n]['within_variance_fraction'],cv.get(n,{}).get('within_sd_after_time_effects')] for n in v])+
        f"\nwithin residual-price rank={r['conditional_within_prices']['residual_price_rank']}، condition={r['conditional_within_prices']['residual_price_condition']:.6f}. time design پس از demeaning خانوار rank=14 از 16 است؛ وابستگی‌های within توسط least squares حذف می‌شوند. این به معنی rank deficiency design سطحی estimator نیست. SDهای گزارش‌شده population SD هستند و variance decomposition بر نمونه سه‌موجی متوازن انجام می‌شود.\n")
    sw=r['switching_source_panel']
    add('purchase switching در Panel B منبع',table(['گروه','000','111','switchers','unknown food wave'],
        [[f'G{i}',*[sw[str(i)][k] for k in ['always_zero','always_positive','switchers','unknown_food_waves']]] for i in range(1,13)]))
    tiers=r['prices']['tiers']['PanelB'];rows=[['همه اقلام',*[100*tiers['overall'][str(i)] for i in range(1,7)]]]
    rows.extend([[f'G{g}',*[100*tiers['by_group'][str(g)][str(i)] for i in range(1,7)]] for g in range(1,13)])
    add('پوشش tier قیمت در Panel B، درصد تخصیص قلم',table(['گروه','T1','T2','T3','T4','T5','T6'],rows)+
        '\nT5/T6 برای اقلام کم‌خرید بیشتر است؛ برنج، گوشت و میوه بیشترین سهم national-season را دارند، با این حال همه ۱۰۶ قلم در هر سال-فصل پشتیبانی نهایی کافی دارند. جزئیات by-year و All در JSON موجود است. در کل ۱۰٬۸۴۱٬۷۵۶ donor وارد quality WLS شدند و فقط ۴ قیمت تعدیل‌شده غیرمثبت از pool کنار گذاشته شد.\n')
    add('تمام وزن‌های ثابت Young و base',table(['گروه','کد قلم','نام قلم','omega fixed','All weighted real expenditure base'],
        [[f'G{x["group_id"]}',str(x['commodity_code']),x['commodity_name'],x['fixed_weight'],x['national_weighted_real_expenditure']] for x in r['prices']['item_weights']])+
        '\n'+table(['گروه','log price center before normalization'],[[f'G{i+1}',v] for i,v in enumerate(r['prices']['price_centers'])]))
    fsfields=['r_squared','excluded_partial_r_squared','excluded_classical_f']
    fsrows=[[k,a['first_stage'][k],b['first_stage'][k]] for k in fsfields]
    fsrows.append(['excluded income cluster Wald',a['first_stage']['excluded_panel_cluster_wald']['statistic'],b['first_stage']['excluded_panel_cluster_wald']['statistic']])
    fsrows.append(['latent current-CF cluster Wald',a['inference_diagnostics']['conditional_cf_current_joint_test']['statistic'],b['inference_diagnostics']['conditional_cf_current_joint_test']['statistic']])
    add('control function و آزمون meanها',table(['diagnostic','Pooled','Mundlak'],fsrows)+
      '\nRF current-income excluded Wald دارای df=2 است؛ در Mundlak p≈7.12e-262. کاهش partial R² پس از شرط‌گذاری بر history طبیعی است: به حدود ۲٫۴٪ می‌رسد و relevance current income هنوز قوی است. این آزمون exclusion را تأیید نمی‌کند. latent current-CF Wald در هر دو دارای df=11 و p<1e-300 است.\n\n'+
      table(['آزمون Mundlak-B','Wald','df','p'],[[k,b['inference_diagnostics'][k]['statistic'],b['inference_diagnostics'][k]['df'],'<1e-300'] for k in ['mundlak_joint_test','mundlak_and_mean_cf_joint_test']])+
      '\nآزمون ۲۲۰ضریبی فقط shifterهای ۲۰ mean برون‌زا در سیستم نهفته است؛ آزمون ۲۳۱ضریبی mean-CF را هم شامل می‌شود. اینها joint test تمام مراحل RF/Probit/QUAIDS با cross-stage covariance نیستند. آزمون‌های meanها در هر Probit جداگانه در جدول بعد آمده‌اند.\n')
    for tag in ['Pooled','CRE']:
        m=r[tag];di=m['participation']
        add(f'participation و S&Y diagnostics: {tag}',table(['گروه','purchase rate','iterations','Phi min','Phi max','CF coefficient','CF cluster p','Mundlak cluster p'],
          [[f'G{x["group"]}',x['participation_rate'],x['iterations'],x['Phi_min'],x['Phi_max'],x['cf_coefficient'],x['cf_panel_cluster_test']['pvalue'],x.get('mundlak_panel_cluster_joint_test',{}).get('pvalue')] for x in di])+
          '\nهمه ۱۲ Probit همگرا شدند و هیچ ستون design حذف نشد. cluster tests برون‌داد RF را fixed می‌گیرند؛ naive CF z نیز برای audit در JSON حفظ شده است.\n')
        pred=m['predictions']
        add(f'fitted shares: {tag}',table(['گروه','mean fitted share','negative fraction','above-one fraction'],
          [[f'G{i+1}',pred['mean_fitted_shares'][i],pred['negative_fitted_fraction'][i],pred['over_one_fitted_fraction'][i]] for i in range(12)])+
          '\nQuantileهای جمع fitted shares در ترتیب min/1%/median/99%/max: '+', '.join(fmt(x) for x in pred['fitted_share_sum_quantiles'])+'. هیچ fitted share بزرگ‌تر از یک نیست. extreme deviations جمع سهم و fitted منفی برای طراحی نسخه نهایی باید بررسی شوند؛ در این اجرا clipping یا حذف post-estimation انجام نشده است.\n')
    add('تمام ضرایب RF کنترل‌فانکشن',table(['نام','Pooled','Mundlak'],
      [[n,a['first_stage']['coefficients'].get(n),b['first_stage']['coefficients'].get(n)] for n in dict.fromkeys(list(a['first_stage']['coefficients'])+list(b['first_stage']['coefficients']))])+
      '\nconstant در RF نخست است. income center مشترک='+fmt(b['first_stage']['income_center'])+'. meanهای income بر centered log و مربع centered log تعریف شده‌اند.\n')
    for tag in ['Pooled','CRE']:
        co=r[tag]['coefficients'];eta=np.array(co['translations_original_units']);cent=np.array(co['translation_centers'])
        a0=np.array(co['alpha_at_center'])-cent@eta
        add(f'تمام ضرایب QUAIDS: {tag}',table(['گروه','alpha centered','alpha at Z=0','beta','lambda','delta SY','kappa CF'],
            [[f'G{i+1}',co['alpha_at_center'][i],a0[i],co['beta'][i],co['lambda'][i],co['delta'][i],co['cf_current'][i]] for i in range(12)])+
            '\nalpha centered به کنترل‌های مرکززدایی‌شده/استانداردشده fitted layer مربوط است. alpha at Z=0 همراه جدول translation در واحد اصلی همان معادله را بازسازی می‌کند؛ بعضی Z=0ها خارج دامنه نمونه‌اند و reference تجربی نیستند.\n')
        add(f'تمام ماتریس gamma: {tag}',matrix(co['gamma']))
        add(f'تمام covariance خطای IFGNLS: {tag}',matrix(r[tag]['error_covariance'])+
            '\nاین Sigma باقیمانده‌های ۱۲ معادله است و در تکرارهای IFGNLS برآورد می‌شود؛ بخشی از theta ضرایب میانگین نیست. covariance ضرایب sandwich و V solver پارامتر ترجیحات نیستند و جای bootstrap نهایی را نمی‌گیرند.\n')
        add(f'تمام translation coefficients در واحد اصلی: {tag}',table(['نام کنترل']+[f'G{i}' for i in range(1,13)],
             [[name,*row] for name,row in zip(co['translation_names'],eta)])+
             '\nهر ردیف sum-to-zero دارد. به ازای کنترل z، shifter برابر coefficient × (z − center) در alpha centered است. rho Ray و تمام eta Ray در native computational core ثابت صفرند و پارامتر برآوردی نیستند؛ جدول حاضر بلوک translation جداست.\n')
        add(f'مرکز و مقیاس تمام کنترل‌ها: {tag}',table(['نام','center','scale'],
             [[name,c,s] for name,c,s in zip(co['translation_names'],co['translation_centers'],co['translation_scales'])])+
             '\nضریب استانداردشده دقیقاً original-unit coefficient × scale است؛ همه standardized coefficients هم در JSON هستند.\n')
        add(f'تمام ضرایب ۱۲ Probit: {tag}',table(['نام regressor']+[f'G{i}' for i in range(1,13)],
             [[name,*row] for name,row in zip(r[tag]['probit_regressor_names'],np.array(r[tag]['probit_coefficients']).T)])+
             '\nاین ضرایب در واحد اصلی regressors هستند؛ constant در آخر است.\n')
        for title,key in [('Marshallian، تمام own/cross-price','marshallian'),('Hicksian با Slutsky convention، تمام own/cross-price','hicksian_slutsky_convention'),('latent Marshallian، تمام own/cross-price','latent_marshallian')]:
            add(f'ماتریس کشش {title}: {tag}',matrix(r[tag]['elasticities'][key]))
        add(f'کشش مخارج نهفته و denominator مرجع: {tag}',table(['گروه','latent expenditure elasticity','censoring-adjusted mean share'],
             [[f'G{i+1}',r[tag]['elasticities']['latent_expenditure'][i],r[tag]['elasticities']['censoring_adjusted_mean_share'][i]] for i in range(12)]))
    add('provenance فایل‌ها',table(['file','SHA256'],[[n,h] for n,h in r['input_hashes'].items()])+
        '\nPanel CSV داخل ZIP SHA256: `'+r['source_manifest']['panel_csv_uncompressed_SHA256']+'`.\n\nبسته D1 قدیمی SHA256: `'+r['source_manifest']['prior_bundle_SHA256']+'`.\n\nproject base commit: `'+r['source_manifest']['project_base_commit']+'`؛ pyquaidsce commit: `'+r['pyquaidsce_commit']+'`.\n')
    block=START+'\n\n'+'\n'.join(sections)+END+'\n'
    if START in text:
        lo=text.index(START);hi=text.index(END,lo)+len(END)
        text=text[:lo]+block+text[hi:].lstrip('\n')
    else:text+='\n'+block
    text=text.replace('\\[\n','$$\n').replace('\\]\n','$$\n')
    args.report.write_text(text)

if __name__=='__main__':main()
