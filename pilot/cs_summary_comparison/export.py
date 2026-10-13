"""Publish only aggregate JSON, CSV, Markdown and Excel outputs."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill

OUT = Path(__file__).resolve().parent


def comparison_frame(data, sample, method):
    common = data['runs'][f'CS_{sample}_common'][f'{method}_overall']
    historical = data['runs'][f'CS_{sample}_history'][f'{method}_overall']
    return pd.DataFrame({'group': data['groups'],
                         'common_expenditure': common['expenditure'],
                         'historical_expenditure': historical['expenditure'],
                         'expenditure_difference': np.array(historical['expenditure'])-common['expenditure'],
                         'common_own_price': np.diag(common['marshallian']),
                         'historical_own_price': np.diag(historical['marshallian']),
                         'own_price_difference': np.diag(np.array(historical['marshallian'])-common['marshallian'])})


def micro_frame(data, sample, stat, label='overall'):
    common = data['runs'][f'CS_{sample}_common']['method3'][label]
    historical = data['runs'][f'CS_{sample}_history']['method3'][label]
    return pd.DataFrame({'group': data['groups'],
                         'common_expenditure': common['expenditure'][stat],
                         'historical_expenditure': historical['expenditure'][stat],
                         'expenditure_difference': np.array(historical['expenditure'][stat])-common['expenditure'][stat],
                         'common_own_price': common['own_price'][stat],
                         'historical_own_price': historical['own_price'][stat],
                         'own_price_difference': np.array(historical['own_price'][stat])-common['own_price'][stat]})


def markdown_table(frame):
    labels = ['گروه', 'مخارج مشترک', 'مخارج تاریخی', 'تفاوت', 'خودی مشترک', 'خودی تاریخی', 'تفاوت']
    lines = ['| '+' | '.join(labels)+' |', '| --- | '+' | '.join(['---:']*6)+' |']
    for row in frame.itertuples(index=False, name=None):
        lines.append('| '+str(row[0])+' | '+' | '.join(f'{v:.4f}' for v in row[1:])+' |')
    return '\n'.join(lines)


def export():
    data = json.loads((OUT/'results.json').read_text())
    def diff(sample, method, group, own=False):
        values = data['comparisons'][sample][method]['marshallian' if own else 'expenditure']
        return values[group][group] if own else values[group]
    book = openpyxl.Workbook(); book.remove(book.active)
    guide = book.create_sheet('Guide')
    notes = [
        'چهار مدل مقطعی؛ پارامترهای ثابت commit 843d9d0؛ هیچ مدل دوباره تخمین زده نشده است.',
        'روش ۱: کشش در میانگین واقعی سه دوره، سپس میانگین با وزن تعداد مشاهدات؛ وزن برابر یک‌سوم استفاده نشده است.',
        'روش ۲: مرجع میانگین کل؛ هر رژیم تاریخی فعال، سپس همان وزن دوره‌ها؛ CF میانگین خاص هر مدل ثابت می‌ماند.',
        'روش ۲ تمام raw controls بین دو مدل همسان‌اند؛ residual CF دو مدل لزوماً برابر نیست و RF دوباره در رژیم فرضی محاسبه نمی‌شود.',
        'روش ۳: میانگین و میانه خانوار–سال؛ گروه‌های دارای سهم غیرمثبت نامعتبرند؛ تمام سهم‌های مثبت حفظ شده‌اند؛ بدون trimming یا winsorization.',
        'میانگین مشاهده‌ای روش ۳ با میانگین مساوی شناسه‌های خانوار در گزارش قبلی یک تعریف ندارد.',
        'Mean/Median comparisons اختلاف خلاصه‌های جداگانه روی موارد معتبر هر مدل‌اند؛ paired-valid در شیت جدا برای اشتراک معتبر دو مدل است.',
        'روش ۲ می‌تواند ترکیب سال/cohort فرضی خارج از حمایت واقعی داده باشد؛ این ارزیابی تابعی، اثر علّی یا اثر خالص پارامترهای QUAIDS نیست.',
        'روش ۳: پس از حذف مقادیر نامعتبر، وزن تجمیع دوره‌ها برای هر گروه شمار موارد معتبر همان گروه است.',
        'همه تفاوت‌ها تاریخی منهای مشترک‌اند؛ بدون SE، bootstrap یا ادعای معناداری آماری.',
        'دادهٔ خانوار و آرایه‌های مشاهده‌ای خصوصی‌اند؛ workbook فقط خروجی‌های تجمیعی دارد.',
    ]
    for note in notes: guide.append([note])
    guide.column_dimensions['A'].width = 125

    def sheet_frame(name, frame):
        sheet = book.create_sheet(name)
        sheet.append(list(frame.columns))
        for row in frame.itertuples(index=False, name=None): sheet.append(list(row))
        return sheet

    def matrix(sheet, label, reference):
        sheet.append([label])
        sheet.append(['گروه / قیمت']+data['groups']+['کشش مخارج'])
        for i, group in enumerate(data['groups']):
            sheet.append([group]+list(reference['marshallian'][i])+[reference['expenditure'][i]])
        sheet.append([])

    report = ['# سه مقایسهٔ کشش مقطعی مشترک و تاریخی', '',
              'تاریخ: ۱۳ اکتبر ۲۰۲۶. مبنا: چهار CS بستهٔ ۱۵، commit `843d9d0`. این بسته محاسبهٔ پس از تخمین است؛ مدل، داده، قیمت و اکسل فعال ۱۴مدلی تغییر نکرده‌اند.', '',
              '## قرارداد محاسبه', '', *['- '+note for note in notes], '',
              'کشش مخارج `1 + dmu_i/dln(x)/mu_i` و مارشالی `dmu_i/dln(p_j)/mu_i - 1(i=j)` است. مشتق کانال مشارکت را دارد؛ CF و کنترل‌ها در شوک جاری ثابت‌اند. میانگین کنترل‌ها و شاخص Probit از مشاهدات همان نقطه گرفته می‌شود. وزن پیمایش در این خلاصه‌ها استفاده نشده است.', '',
              'در جملهٔ آغازین متن پیوست «وزن یکسان برای هر دوره» آمده، ولی معادله، بخش ۶ و دستور اجرایی آن صریحاً `N_r/N` را تعیین می‌کنند. این محاسبه از دستور دقیق شمار مشاهدات پیروی می‌کند.', '',
              '## وزن‌های دوره', '', '| نمونه | ۱۳۹۲–۱۳۹۶ | ۱۳۹۷–۱۳۹۸ | ۱۳۹۹–۱۴۰۳ |', '| --- | ---: | ---: | ---: |']
    for sample in ('All', 'B'):
        weights = data['runs'][f'CS_{sample}_common']['period_weights']
        report.append('| '+sample+' | '+' | '.join(f'{v:.6f}' for v in weights)+' |')

    for method, title in [('method1', 'روش اول: نقاط واقعی دوره‌ها'), ('method2', 'روش دوم: مرجع مشترک کل نمونه')]:
        report += ['', '## '+title, '']
        for sample in ('All', 'B'):
            frame = comparison_frame(data, sample, method)
            frame.to_csv(OUT/f'{sample}_{method}_comparison.csv', index=False)
            sheet_frame(f'{sample}_{method}', frame)
            report += ['### '+sample, '', markdown_table(frame), '']

    report += ['## روش سوم: کشش‌های مشاهده‌ای کل نمونه', '',
               'در جدول‌های زیر، میانگین/میانه برای هر مدل روی کشش‌های معتبر همان مدل محاسبه می‌شود؛ تعداد مقادیر معتبر دو مدل لزوماً برابر نیست. مقایسهٔ اشتراک معتبر نیز جدا منتشر شده است.', '']
    period_rows = []; diagnostic_rows = []; paired_rows = []
    for sample in ('All', 'B'):
        for stat, title in [('mean', 'میانگین'), ('median', 'میانه')]:
            frame = micro_frame(data, sample, stat)
            sheet_frame(f'{sample}_{stat}', frame)
            frame.to_csv(OUT/f'{sample}_method3_{stat}_comparison.csv', index=False)
            report += [f'### {sample} — {title}', '', markdown_table(frame), '']
        for model in ('common', 'history'):
            name = f'CS_{sample}_{model}'; run = data['runs'][name]
            sheet = book.create_sheet(name+'_matrices')
            matrix(sheet, 'روش ۱ — خلاصهٔ سه نقطهٔ واقعی', run['method1_overall'])
            for code in range(3): matrix(sheet, 'روش ۱ — '+data['periods'][code], run['method1_period_points'][str(code)])
            matrix(sheet, 'روش ۲ — خلاصهٔ مرجع مشترک', run['method2_overall'])
            for code in range(3): matrix(sheet, 'روش ۲ — '+data['periods'][code], run['method2_reference_points'][str(code)])
            for label, stats in run['method3'].items():
                for stat in ('mean', 'median'):
                    matrix(sheet, f'روش ۳ — {label} — {stat}',
                           {'expenditure': stats['expenditure'][stat], 'marshallian': stats[f'marshallian_{stat}']})
                for i, group in enumerate(data['groups']):
                    period_rows.append({'model': name, 'period': label, 'group': group,
                                        **{f'{kind}_{stat}': stats[kind][stat][i]
                                           for kind in ('expenditure', 'own_price') for stat in ('mean', 'median', 'p01', 'p99')},
                                        'invalid_share_count': stats['invalid_share_count'][i]})
                    diagnostic_rows.append({'model': name, 'period': label, 'group': group, 'rows': stats['rows'],
                                            'invalid_share_count': stats['invalid_share_count'][i],
                                            'positive_share_below_1e_6': stats['positive_share_below_1e_6_count'][i],
                                            **{f'{kind}_{stat}': stats[kind][stat][i]
                                               for kind in ('expenditure', 'own_price')
                                               for stat in ('valid_count', 'absolute_above_100_count', 'min', 'max')}})
        for label, stats in data['comparisons'][sample]['method3_paired_valid'].items():
            for kind, summary in stats.items():
                for i, group in enumerate(data['groups']):
                    paired_rows.append({'sample': sample, 'period': label, 'kind': kind, 'group': group,
                                        **{key: values[i] for key, values in summary.items()}})
    for name, rows in [('Period_distributions', period_rows), ('Diagnostics', diagnostic_rows), ('Paired_valid', paired_rows)]:
        frame = pd.DataFrame(rows)
        frame.to_csv(OUT/f'{name}.csv', index=False)
        sheet_frame(name, frame)

    # Keep a full period-level comparison in the report as requested.
    report += ['## روش سوم به تفکیک دوره', '']
    for sample in ('All', 'B'):
        for code in range(3):
            for stat, title in [('mean', 'میانگین'), ('median', 'میانه')]:
                report += [f"### {sample} — {data['periods'][code]} — {title}", '',
                           markdown_table(micro_frame(data, sample, stat, f'period_{code}')), '']

    report += ['## نتیجهٔ مقایسه و حدود تفسیر', '',
               f"روش اول، اعداد نان در متن پیوست را بازتولید می‌کند: اختلاف مخارج تاریخی منهای مشترک در All={diff('All', 'method1', 1):+.6f} و در B={diff('B', 'method1', 1):+.6f}. اختلاف گزارش قدیمی B={data['comparisons']['B']['old_comparison']['expenditure'][1]:+.6f} بود و علامت آن با هم‌تعریف‌کردن خلاصه تغییر می‌کند.",
               f"بزرگ‌ترین اختلاف خودقیمتی روش اول برای روغن است: {diff('All', 'method1', 4, True):+.6f} در All و {diff('B', 'method1', 4, True):+.6f} در B. روش دوم هم اختلاف منفی روغن را حفظ می‌کند: {diff('All', 'method2', 4, True):+.6f} و {diff('B', 'method2', 4, True):+.6f}. تفاوت قند/شیرینی و ادویه نیز در هر دو روش منفی است؛ اندازه‌ها در جداول آمده‌اند.",
               f"همه نتیجه‌ها در دو مرجع پایدار نیستند. اختلاف خودقیمتی مغزها در روش اول {diff('All', 'method1', 8, True):+.6f} برای All و {diff('B', 'method1', 8, True):+.6f} برای B است، اما در روش دوم {diff('All', 'method2', 8, True):+.6f} و {diff('B', 'method2', 8, True):+.6f} می‌شود. اختلاف مخارج برنج و میوه از اعداد نزدیک صفر/منفی در روش اول به مثبت حدود 0.15–0.21 در مرجع مشترک می‌رسد. بنابراین انتخاب نقطهٔ ارزیابی برای این یافته‌ها مهم است.",
               f"در روش سوم، اختلاف میانگین مخارج نان {data['comparisons']['All']['method3_separate_valid']['overall']['expenditure']['mean'][1]:+.6f} در All و {data['comparisons']['B']['method3_separate_valid']['overall']['expenditure']['mean'][1]:+.6f} در B است، ولی اختلاف میانه فقط {data['comparisons']['All']['method3_separate_valid']['overall']['expenditure']['median'][1]:+.6f} و {data['comparisons']['B']['method3_separate_valid']['overall']['expenditure']['median'][1]:+.6f} است. دنبالهٔ کشش‌های افراطی و تفاوت موارد معتبر بخشی از اختلاف میانگین‌اند؛ اختلاف نان را نباید پاسخ نمایندهٔ بیشتر خانوارها تعبیر کرد.",
               'در مدل تاریخی نیز مقادیر افراطی و سهم‌های منفی وجود دارند؛ جدول Diagnostics تعداد و دامنه را برای هر گروه/دوره ثبت می‌کند. Paired_valid مقایسه را به همان مشاهدات دارای کشش معتبر در هر دو مدل محدود می‌کند؛ این حساسیت به حذف، جایگزین تعریف اصلی یا آزمون آماری نیست.',
               'روش دوم قیمت، مخارج و raw controls پایه را میان دو مدل ثابت نگه می‌دارد؛ اما هر مدل باقیماندهٔ CF خود را دارد. درون مدل تاریخی، میانگین CF ثابت می‌ماند و تعامل‌های جاری مشارکت با رژیم تغییر می‌کنند. این دقیقاً قرارداد common_reference_period موجود است، نه مداخلهٔ تازه در RF.',
               'برای B، میانگین cohort/سال در مرجع مشترک می‌تواند با رژیم تاریخی فرضی سازگار با هیچ خانوار واقعی نباشد. برای All نیز دامی سالِ میانگین کنار رژیم فرضی از حمایت دورهٔ واقعی خارج می‌شود. این نقطه یک حساسیت فرم تابعی است و نباید به‌عنوان پاسخ شناسایی‌شدهٔ خانوار مشترک یا تغییر علّی ترجیحات معرفی شود.',
               'این محاسبات، اختلاف معماری کامل common/history را بررسی می‌کنند: RF، Probit و تقاضا بین مدل‌ها فرق دارند. اثر خالص beta/Gamma/lambda تفکیک نشده است. استنباط نهایی با لحاظ مراحل تولیدشده و وابستگی برآوردها هنوز لازم است.', '',
               '## کنترل صحت و بازتولید', '',
               'چهار سیستم از پارامترهای JSON بازسازی شدند؛ کنترل ضرایب مقید و ترجمه‌ها، هش نمونه‌ها، بازتولید نقاط تاریخی/مرجع قبلی، تطابق شمار سهم‌های منفی، تفاضل محدود مشتق‌ها روی نقاط معمول و افراطی، تجمیع میانگین دوره‌ها با شمار معتبر، و هویت تفکیک اختلاف قدیمی بررسی شدند. فایل tests.py این قراردادهای ذخیره‌شده را مستقل از ریزداده کنترل می‌کند.', '',
               'بازتولید:', '', '```bash', 'python -m pip install -r pilot/requirements.txt',
               'python -m pilot.cs_summary_comparison.prepare --inputs intermediate/pilot_inputs',
               'python -m pilot.cs_summary_comparison.run', 'python -m pilot.cs_summary_comparison.export',
               'python -m unittest pilot.cs_summary_comparison.tests', '```', '',
               'گزینهٔ --work مسیر cache خصوصی را تعیین می‌کند؛ فقط sample pickleهای ساخته‌شده و مورد اعتماد پروژه خوانده شوند. ورودی clean و mapping طبق هش ثابت کنترل می‌شوند. آرایه‌های کشش مشاهده‌ای در work خصوصی‌اند. results.json و CSVها و اکسل فقط اطلاعات تجمیعی دارند. منبع پارامتر و هش آن در results.json ثبت شده است.']
    for sheet in book:
        sheet.sheet_view.rightToLeft = True
        sheet.freeze_panes = 'B2' if sheet.title != 'Guide' else None
        if sheet.title != 'Guide':
            sheet.column_dimensions['A'].width = 29
            for col in range(2, sheet.max_column+1): sheet.column_dimensions[openpyxl.utils.get_column_letter(col)].width = 19
        for row in sheet:
            is_header = row[0].value in ('group', 'model', 'sample', 'گروه / قیمت')
            for cell in row:
                cell.alignment = Alignment(wrap_text=True, vertical='center')
                if isinstance(cell.value, float): cell.number_format = '0.0000'
                if is_header:
                    cell.font = Font(bold=True, color='FFFFFF')
                    cell.fill = PatternFill('solid', fgColor='203864')
            sheet.row_dimensions[row[0].row].height = 35
    book.save(OUT/'CS_common_history_three_methods.xlsx')
    (OUT/'report.md').write_text('\n'.join(report)+'\n')
    # Read back every comparison value; Excel should reproduce aggregate JSON.
    readback = openpyxl.load_workbook(OUT/'CS_common_history_three_methods.xlsx', data_only=True)
    for sample in ('All', 'B'):
        for method in ('method1', 'method2'):
            frame = comparison_frame(data, sample, method)
            sheet = readback[f'{sample}_{method}']
            for i in range(12):
                for j in range(1, 7): assert abs(sheet.cell(i+2, j+1).value-frame.iloc[i, j]) < 1e-12
    print('EXPORTED', len(readback.sheetnames), 'sheets', flush=True)


if __name__ == '__main__': export()
