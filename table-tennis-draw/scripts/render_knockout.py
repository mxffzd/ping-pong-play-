"""Render a public knockout PDF and PNG from knockout.py's internal plan JSON."""
import argparse
import json
import math
import os
import shutil
import subprocess
from pathlib import Path


def render(plan, folder, normal_font, bold_font, pdftoppm):
    if not isinstance(plan, dict):
        raise ValueError('淘汰赛编排必须为 JSON 对象')
    from pypdf import PdfReader
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A3, landscape
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    n = plan.get('bracket_size')
    slots = plan.get('slots', [])
    if type(n) is not int or n < 2 or n > 64 or n & (n - 1) or len(slots) != n or [s.get('position') for s in slots] != list(range(1, n + 1)):
        raise ValueError('签表规模或签位无效')
    pdf = folder / '淘汰赛对战图.pdf'
    png = folder / '淘汰赛对战图.png'
    if pdf.exists() or png.exists():
        raise ValueError('对战图已存在，请使用新版本目录')
    if not normal_font.is_file() or not bold_font.is_file():
        raise ValueError('中文字体不存在，请用 --font 和 --bold-font 指定实际字体')
    if not pdftoppm or not Path(pdftoppm).is_file():
        raise ValueError('需要可用的 pdftoppm 路径，才能生成并核对 PNG')
    pdfmetrics.registerFont(TTFont('KnockoutYaHei', str(normal_font), subfontIndex=0))
    pdfmetrics.registerFont(TTFont('KnockoutYaHeiBold', str(bold_font), subfontIndex=0))
    rounds = int(math.log2(n))
    widths = [210] + [160] * rounds
    xs = [68]
    for i in range(rounds):
        xs.append(xs[-1] + widths[i] + 58)
    width = max(landscape(A3)[0], xs[-1] + widths[-1] + 36)
    height = max(landscape(A3)[1], (n - 1) * 34 + 330)
    top = height - 131
    ys = [top - 34 * i for i in range(n)]
    # Small brackets use more vertical separation without changing the type size.
    if n < 16:
        step = min(85, (height - 330) / max(1, n - 1))
        ys = [top - step * i for i in range(n)]
    c = canvas.Canvas(str(pdf), pagesize=(width, height), pageCompression=1)
    title = f'乒乓球{n}强淘汰赛对战图'
    c.setTitle(title)
    c.setAuthor('')
    c.setSubject(f"{plan['group_count']}组，每组前2名出线")
    black = colors.HexColor('#000000')
    muted = colors.HexColor('#64748B')
    edge = colors.HexColor('#CBD5E1')

    def text(x, y, value, size=11, bold=False, color=black, center=False):
        font = 'KnockoutYaHeiBold' if bold else 'KnockoutYaHei'
        length = pdfmetrics.stringWidth(value, font, size)
        left = x - length / 2 if center else x
        if left < 18 or left + length > width - 18:
            raise ValueError(f'文字超出画布：{value}')
        c.setFillColor(color)
        c.setFont(font, size)
        (c.drawCentredString if center else c.drawString)(x, y, value)

    def fit(value, maximum, size=11, bold=False):
        font = 'KnockoutYaHeiBold' if bold else 'KnockoutYaHei'
        if pdfmetrics.stringWidth(value, font, size) <= maximum:
            return value
        while value and pdfmetrics.stringWidth(value + '…', font, size) > maximum:
            value = value[:-1]
        return value + '…'

    def box(x, y, w, h, fill=colors.white, dashed=False):
        c.setFillColor(fill)
        c.setStrokeColor(edge)
        c.setLineWidth(0.8)
        c.setDash([3, 2] if dashed else [])
        c.roundRect(x, y, w, h, 4, stroke=1, fill=1)
        c.setDash([])

    text(36, height - 43, title, size=23, bold=True)
    mode = '小组第二待抽签' if plan['draw_status'] == 'runners_pending' else ('按已登记名次完成第二名抽签' if plan['draw_status'] == 'drawn_actual' else '小组第二名次占位已抽签')
    text(36, height - 67, f"{plan['group_count']}组，每组前2名出线；{mode}。", size=10.5, color=muted)
    for index, x in enumerate(xs):
        count = n // (2 ** index)
        label = '冠军' if count == 1 else '决赛选手' if count == 2 else '四强' if count == 4 else '八强' if count == 8 else f'{count}强'
        text(x + widths[index] / 2, height - 92, label, size=13, bold=True, center=True)
        c.setStrokeColor(edge)
        c.line(x, height - 102, x + widths[index], height - 102)
    middle = (ys[n // 2 - 1] + ys[n // 2]) / 2
    for label, low, high, fill in [('上半区', middle + 2, ys[0] + 20, '#F4F8FD'),
                                    ('下半区', ys[-1] - 20, middle - 2, '#F8FAFC')]:
        c.setFillColor(colors.HexColor(fill))
        c.roundRect(30, low, 480, high - low, 6, stroke=0, fill=1)
        c.saveState()
        c.translate(43, (low + high) / 2)
        c.rotate(90)
        c.setFont('KnockoutYaHeiBold', 10)
        c.setFillColor(black)
        c.drawCentredString(0, 0, label)
        c.restoreState()
    stages = [ys]
    for stage in range(rounds):
        source = stages[-1]
        targets = [(source[i] + source[i + 1]) / 2 for i in range(0, len(source), 2)]
        x1, x2 = xs[stage] + widths[stage], xs[stage + 1]
        join = (x1 + x2) / 2
        c.setStrokeColor(muted)
        c.setLineWidth(1)
        for i, y in enumerate(targets):
            a, b = source[2 * i:2 * i + 2]
            c.line(x1, a, join, a)
            c.line(x1, b, join, b)
            c.line(join, b, join, a)
            c.line(join, y, x2, y)
        stages.append(targets)
    for slot, y in zip(slots, ys):
        text(56, y - 3, str(slot['position']), size=8, color=muted, center=True)
        pending = slot['group'] is None
        participant = slot.get('participant')
        # Public labels are reconstructed from allowed fields; internal seed data is never read.
        label = '小组第二（待抽签）' if pending else f"第{slot['group']}组{'第一' if slot['rank'] == 1 else '第二'}"
        box(xs[0], y - 13.5, widths[0], 27, colors.HexColor('#FFF8E8') if pending else colors.white, pending)
        if participant:
            text(xs[0] + 10, y + 2, fit(participant['name'], 188, 10.5), size=10.5, bold=True)
            text(xs[0] + 10, y - 9, fit(f"{label}  {participant['id']}", 188, 7.5), size=7.5, color=muted)
        else:
            text(xs[0] + 12, y - 4, label, size=11, bold=slot['rank'] == 1)
    match = 0
    for stage in range(1, rounds + 1):
        for y in stages[stage]:
            match += 1
            final = stage == rounds
            box(xs[stage], y - (34 if final else 17), widths[stage], 68 if final else 34,
                colors.HexColor('#FFF3D6') if final else colors.white)
            if final:
                text(xs[stage] + 80, y + 10, '冠军', size=18, bold=True, center=True)
                text(xs[stage] + 80, y - 7, f'第{match}场胜者', size=9, color=muted, center=True)
                line_y = y - 23
            else:
                text(xs[stage] + 11, y + 3, f'第{match}场胜者', size=9.5, color=muted)
                line_y = y - 9
            c.setStrokeColor(edge)
            c.setLineWidth(0.6)
            c.line(xs[stage] + 11, line_y, xs[stage] + widths[stage] - 11, line_y)
    if match != n - 1:
        raise ValueError('晋级连线场次校验失败')
    c.setStrokeColor(edge)
    c.line(36, 153, width - 36, 153)
    text(36, 133, '第二名抽签安排' if plan['draw_status'] == 'runners_pending' else '第二名分区', size=11, bold=True)
    y = 114
    for pool in plan['runner_pools']:
        half = '上半区' if pool['half'] == 'upper' else '下半区'
        groups = '、'.join(str(x) for x in pool['groups']) or '无'
        positions = '、'.join(str(x) for x in pool['positions']) or '无'
        value = f'{half}：第{groups}组第二，对应 {positions} 号签位。'
        # Large brackets get extra horizontal canvas space, keeping this readable.
        text(36, y, value, size=9 if n <= 32 else 8.5)
        y -= 20
    text(36, 64, '晋级方式', size=11, bold=True)
    text(104, 64, '各场胜者依连线进入下一轮，直至决出冠军。', size=9.5)
    text(36, 42, '同组第一、第二分处不同半区，最早在决赛再次相遇。', size=9.5, color=muted)
    c.showPage()
    c.save()
    reader = PdfReader(pdf)
    extracted = reader.pages[0].extract_text()
    if len(reader.pages) != 1 or any(f'第{i}场胜者' not in extracted for i in range(1, n)):
        raise ValueError('PDF 场次文字校验失败')
    # The renderer never uses seed_basis, tier_checks or warnings on public pages.
    dpi = min(160, 72 * 3600 / max(width, height))
    run = subprocess.run([str(pdftoppm), '-png', '-singlefile', '-r', str(dpi), str(pdf), str(png.with_suffix(''))],
                         capture_output=True, text=True)
    if run.returncode or not png.is_file():
        raise ValueError('PDF 已生成，PNG 渲染失败：' + run.stderr[:300])
    return pdf, png


def main():
    parser = argparse.ArgumentParser(description='生成不标注种子的淘汰赛公开对战图')
    parser.add_argument('--input', type=Path, required=True)
    fonts = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts'
    parser.add_argument('--font', type=Path, default=fonts / 'msyh.ttc')
    parser.add_argument('--bold-font', type=Path, default=fonts / 'msyhbd.ttc')
    parser.add_argument('--pdftoppm', default=shutil.which('pdftoppm'))
    args = parser.parse_args()
    try:
        plan = json.loads(args.input.read_text(encoding='utf-8-sig'))
        pdf, png = render(plan, args.input.parent, args.font, args.bold_font, args.pdftoppm)
    except (OSError, ValueError, KeyError, TypeError, ImportError) as error:
        parser.exit(2, f'对战图未完成：{error}\n')
    print(json.dumps({'pdf': str(pdf.resolve()), 'png': str(png.resolve()), 'public_seed_labels': False}, ensure_ascii=False))


if __name__ == '__main__':
    main()
