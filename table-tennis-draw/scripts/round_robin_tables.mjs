// Reusable worksheet authoring helper. Pass a Workbook from the spreadsheet skill.
export function addRoundRobinTables(workbook, schedule) {
  const listName = '循环赛对阵';
  const matrixName = '组内循环表';
  const existing = workbook.worksheets.items.map(s => s.name);
  if (existing.includes(listName) || existing.includes(matrixName)) {
    throw new Error('循环赛工作表已存在，请保留已录入的比分并进行定向更新。');
  }
  const matches = schedule.matches;
  const list = workbook.worksheets.add(listName);
  const matrix = workbook.worksheets.add(matrixName);
  const font = 'Microsoft YaHei';
  const blue = '#DBEAFE';
  const last = Math.max(7, matches.length + 6);
  function base(sheet, range) {
    sheet.showGridLines = false;
    sheet.getRange(range).format.font = { name: font, size: 11, color: '#000000' };
    sheet.getRange(range).format.rowHeight = 25;
    sheet.getRange(range).format.verticalAlignment = 'center';
    sheet.getRange(range).format.wrapText = false;
    sheet.getRange('A2').format.font = { name: font, size: 16, bold: true, color: '#000000' };
    sheet.getRange('A2').format.rowHeight = 32;
  }
  function header(sheet, range) {
    sheet.getRange(range).format = { fill: blue, font: { name: font, size: 11, bold: true, color: '#000000' },
      horizontalAlignment: 'center', rowHeight: 28, borders: { bottom: { style: 'thin', color: '#94A3B8' } } };
  }
  function literal(s) { return String(s).startsWith('=') ? "'" + s : s; }
  base(list, `A1:N${Math.max(last + 1, (schedule.byes || []).length + 7)}`);
  list.getRange('A2').values = [['组内单循环对阵']];
  list.getRange('A3').values = [['黄色格填双方赢得局数；空白表示未录入。']];
  list.getRange('A4').values = [['按组别、轮次排列，场地与时间另行安排。']];
  list.getRange('H3').values = [['已录入场数']];
  list.getRange('I3').formulas = [[`=COUNTIFS(J7:J${last},"已录入")`]];
  list.getRange('H4:I4').values = [['总场数', matches.length]];
  [15, 8, 8, 14, 14, 14, 14, 13, 13, 17, 3, 8, 8, 22].forEach((w, i) => {
    list.getRangeByIndexes(0, i, Math.max(last + 1, (schedule.byes || []).length + 7), 1).format.columnWidth = w;
  });
  list.getRange('A6:J6').values = [['比赛编号', '组别', '轮次', '甲编号', '甲姓名', '乙编号', '乙姓名', '甲局数', '乙局数', '录入状态']];
  header(list, 'A6:J6');
  const matchRows = new Map();
  const pairRows = new Map();
  const pairKey = (group, a, b) => JSON.stringify([group, ...[a, b].sort()]);
  if (matches.length) {
    list.getRange(`A7:J${last}`).values = matches.map(m => [m.match_id, m.group, m.round,
      literal(m.player_a_id), literal(m.player_a_name), literal(m.player_b_id), literal(m.player_b_name), null, null, null]);
    list.getRange(`H7:I${last}`).format.fill = '#FFF2CC';
    list.getRange(`B7:D${last}`).format.horizontalAlignment = 'center';
    list.getRange(`F7:F${last}`).format.horizontalAlignment = 'center';
    list.getRange(`H7:J${last}`).format.horizontalAlignment = 'center';
    list.getRange(`J7:J${last}`).formulas = matches.map((m, i) => {
      const r = i + 7;
      matchRows.set(m.match_id, r);
      pairRows.set(pairKey(m.group, m.player_a_id, m.player_b_id), { row: r, match: m });
      return [`=IF(COUNTA(H${r}:I${r})=0,"待录入",IF(COUNTA(H${r}:I${r})<2,"待补全",IF(COUNT(H${r}:I${r})<>2,"比分无效",IF(OR(H${r}<0,I${r}<0,H${r}<>INT(H${r}),I${r}<>INT(I${r}),H${r}=I${r}),"比分无效","已录入"))))`];
    });
    list.getRange(`J7:J${last}`).conditionalFormats.add('containsText', { text: '比分无效',
      format: { fill: '#FEE2E2', font: { color: '#B91C1C', bold: true } } });
  }
  if (schedule.byes?.length) {
    list.getRange('L6:N6').values = [['组别', '轮次', '轮空选手']];
    list.getRange(`L7:N${schedule.byes.length + 6}`).values = schedule.byes.map(b => [b.group, b.round, literal(`${b.player_name} ${b.player_id}`)]);
    header(list, 'L6:N6');
    list.getRange(`N7:N${schedule.byes.length + 6}`).format.columnWidth = 30;
  }
  list.freezePanes.freezeRows(6);

  const nMax = Math.max(...schedule.groups.map(g => g.players.length));
  const perRow = nMax <= 6 ? Math.min(2, schedule.groups.length) : 1;
  const blockWidth = nMax + 3;
  const stride = nMax + 5;
  const cols = perRow * blockWidth + (perRow - 1);
  const rows = 5 + Math.ceil(schedule.groups.length / perRow) * stride;
  function address(row, col) {
    let letters = '', c = col + 1;
    while (c) { c--; letters = String.fromCharCode(65 + c % 26) + letters; c = Math.floor(c / 26); }
    return `${letters}${row + 1}`;
  }
  base(matrix, `A1:${address(rows - 1, cols - 1)}`);
  matrix.getRange('A2').values = [['组内循环对战表']];
  matrix.getRange('A3').values = [[`${schedule.groups.length}组，共${matches.length}场；比分在“循环赛对阵”黄色格录入。`]];
  matrix.getRange('A4').values = [['矩阵以行选手局数在前，空白表示未完成有效录入。']];
  for (let col = 0; col < cols; col++) {
    const offset = col % (blockWidth + 1);
    matrix.getRangeByIndexes(0, col, rows, 1).format.columnWidth = offset === 0 ? 7 : offset === 1 ? 14 : offset === 2 ? 14 : offset === blockWidth ? 3 : 10;
  }
  const bindings = [];
  schedule.groups.forEach((group, index) => {
    const top = 5 + Math.floor(index / perRow) * stride; // one-based title row
    const left = (index % perRow) * (blockWidth + 1);
    const n = group.players.length;
    const section = matrix.getRangeByIndexes(top - 1, left, 1, n + 3);
    section.format = { fill: blue, font: { name: font, size: 12, bold: true, color: '#000000' }, rowHeight: 29 };
    matrix.getRangeByIndexes(top - 1, left, 1, 1).values = [[`第${group.group}组（${n}人，${n * (n - 1) / 2}场）`]];
    const nameCounts = new Map();
    group.players.forEach(p => nameCounts.set(p.name, (nameCounts.get(p.name) || 0) + 1));
    const playerHeads = group.players.map(p => nameCounts.get(p.name) > 1 ? `${p.name}\n${p.id}` : String(p.name));
    const heads = ['序号', '参赛编号', '姓名', ...playerHeads.map(literal)];
    matrix.getRangeByIndexes(top, left, 1, n + 3).values = [heads];
    header(matrix, `${address(top, left)}:${address(top, left + n + 2)}`);
    matrix.getRangeByIndexes(top, left + 3, 1, n).format.wrapText = true;
    if (playerHeads.some(name => name.includes('\n') || name.length > 4)) {
      matrix.getRangeByIndexes(top, left, 1, n + 3).format.rowHeight = 44;
    }
    matrix.getRangeByIndexes(top + 1, left, n, 3).values = group.players.map((p, i) => [i + 1, literal(p.id), literal(p.name)]);
    matrix.getRangeByIndexes(top + 1, left, n, 2).format.horizontalAlignment = 'center';
    const grid = matrix.getRangeByIndexes(top + 1, left + 3, n, n);
    grid.format.horizontalAlignment = 'center';
    grid.format.borders = { preset: 'all', style: 'thin', color: '#CBD5E1' };
    group.players.forEach((a, i) => group.players.forEach((b, j) => {
      const cell = address(top + 1 + i, left + 3 + j);
      if (i === j) {
        matrix.getRange(cell).values = [['—']];
        matrix.getRange(cell).format.fill = '#E2E8F0';
      } else {
        const source = pairRows.get(pairKey(group.group, a.id, b.id));
        if (!source) throw new Error('循环赛对阵缺少矩阵对应的比赛');
        const { row, match } = source;
        const aColumn = match.player_a_id === a.id ? 'H' : 'I';
        const bColumn = aColumn === 'H' ? 'I' : 'H';
        matrix.getRange(cell).formulas = [[`=IF('${listName}'!J${row}="已录入",'${listName}'!${aColumn}${row}&":"&'${listName}'!${bColumn}${row},"")`]];
        bindings.push({ match_id: match.match_id, player_id: a.id, cell, source_row: row, aColumn, bColumn });
      }
    }));
  });
  return { list, matrix, matchRows, bindings, matrixRange: `A1:${address(rows - 1, cols - 1)}`,
    listRange: `A1:${schedule.byes?.length ? 'N' : 'J'}${last + 1}` };
}
