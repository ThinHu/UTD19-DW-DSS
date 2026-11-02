// Sinh tài liệu thiết kế DSS v5 (.docx) theo mẫu v4, số liệu đọc từ data/dss/meta.json
// Chạy: node docs/build_design_doc.js data/dss/meta.json docs/DSS_Thiet_ke_giai_doan1_Vinh_v5.docx
const fs = require('fs')
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, WidthType, ShadingType, AlignmentType,
  HeadingLevel, BorderStyle, LevelFormat, PageBreak, TableOfContents, Footer, PageNumber, TableLayoutType, ImageRun,
} = require('docx')
const path = require('path')

const meta = JSON.parse(fs.readFileSync(process.argv[2] || 'data/dss/meta.json', 'utf8'))
const OUT = process.argv[3] || 'docs/DSS_Thiet_ke_giai_doan1_Vinh_v5.docx'
const EVP = process.argv[4] || 'reports/dss_evaluation.json'
const EV = fs.existsSync(EVP) ? JSON.parse(fs.readFileSync(EVP, 'utf8')) : null
const IMG_INFLUENCE = path.join(__dirname, 'img', 'influence_diagram.png')   // chụp từ tab Mô hình quyết định
const WEATHER_EXP = path.join(__dirname, 'weather_experiment.json')          // thử nghiệm thêm thời tiết vào C5
const WX = fs.existsSync(WEATHER_EXP) ? JSON.parse(fs.readFileSync(WEATHER_EXP, 'utf8')) : null
const strat = (prefix) => (EV ? EV.strategies.find((r) => r.strategy.startsWith(prefix)) : null)

const BLUE = '1F4E79', W = 9540
const vn = (x, d = 0) => {
  if (x === null || x === undefined || Number.isNaN(x)) return '—'
  const s = Number(x).toFixed(d)
  const [a, b] = s.split('.')
  const ai = a.replace(/\B(?=(\d{3})+(?!\d))/g, '.')
  return b ? `${ai},${b}` : ai
}
const pc = (x, d = 1) => `${vn(x * 100, d)}%`
const dmy = (s) => { const [y, m, d] = s.split('-'); return `${d}/${m}/${y}` }

// ---------- khối dựng ----------
const runs = (text, base = {}) => {
  // hỗ trợ **đậm** trong chuỗi
  const parts = String(text).split(/(\*\*[^*]+\*\*)/g).filter(Boolean)
  return parts.map((p) => p.startsWith('**') ? new TextRun({ ...base, text: p.slice(2, -2), bold: true }) : new TextRun({ ...base, text: p }))
}
const P = (text, o = {}) => new Paragraph({ spacing: { after: 160, line: 300 }, ...o, children: runs(text, o.run || {}) })
const H1 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_1, spacing: { before: 360, after: 160 }, children: [new TextRun({ text: t, bold: true, color: BLUE })] })
const H2 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_2, spacing: { before: 240, after: 120 }, children: [new TextRun({ text: t, bold: true, color: BLUE })] })
const H3 = (t) => new Paragraph({ spacing: { before: 200, after: 100 }, children: [new TextRun({ text: t, bold: true, color: BLUE })] })
const B = (t, lvl = 0) => new Paragraph({ numbering: { reference: 'bul', level: lvl }, spacing: { after: 60, line: 288 }, children: runs(t) })
const N = (t) => new Paragraph({ numbering: { reference: 'num', level: 0 }, spacing: { after: 60, line: 288 }, children: runs(t) })
const brk = () => new Paragraph({ children: [new PageBreak()] })

const cellMargins = { top: 80, bottom: 80, left: 120, right: 120 }
const border = { style: BorderStyle.SINGLE, size: 4, color: 'BFBFBF' }
const borders = { top: border, bottom: border, left: border, right: border }

function box(title, items, fill = 'FFF2CC', line = 'D6B656') {
  const b = { style: BorderStyle.SINGLE, size: 4, color: line }
  const kids = [new Paragraph({ spacing: { after: 80 }, children: [new TextRun({ text: title, bold: true })] })]
  items.forEach((it) => kids.push(typeof it === 'string' ? B(it) : it))
  return [new Table({
    width: { size: W, type: WidthType.DXA }, columnWidths: [W], layout: TableLayoutType.FIXED,
    rows: [new TableRow({ children: [new TableCell({
      width: { size: W, type: WidthType.DXA }, borders: { top: b, bottom: b, left: b, right: b },
      shading: { fill, type: ShadingType.CLEAR, color: 'auto' }, margins: { top: 140, bottom: 140, left: 180, right: 180 }, children: kids,
    })] })],
  }), new Paragraph({ spacing: { after: 120 }, children: [] })]
}

function formula(lines, note) {
  const b = { style: BorderStyle.SINGLE, size: 4, color: BLUE }
  const kids = lines.map((l) => new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 60 }, children: [new TextRun({ text: l, bold: true, size: 26, color: BLUE })] }))
  if (note) kids.push(new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: note, italics: true, color: '595959' })] }))
  return [new Table({
    width: { size: W, type: WidthType.DXA }, columnWidths: [W],
    rows: [new TableRow({ children: [new TableCell({ width: { size: W, type: WidthType.DXA }, borders: { top: b, bottom: b, left: b, right: b },
      shading: { fill: 'F2F2F2', type: ShadingType.CLEAR, color: 'auto' }, margins: { top: 160, bottom: 160, left: 180, right: 180 }, children: kids })] })],
  }), new Paragraph({ spacing: { after: 120 }, children: [] })]
}

// table(headers, rows, widthsRatio, opts) ; cell value may be string or {t, fill, bold}
function table(head, rows, ratio, opts = {}) {
  const tot = ratio.reduce((a, b) => a + b, 0)
  const widths = ratio.map((r) => Math.floor((W * r) / tot))
  widths[widths.length - 1] += W - widths.reduce((a, b) => a + b, 0)
  const mk = (v, i, isHead, rowFill) => {
    const o = typeof v === 'object' && v !== null ? v : { t: v }
    const right = opts.num && opts.num.includes(i) && !isHead
    return new TableCell({
      width: { size: widths[i], type: WidthType.DXA }, borders, margins: cellMargins,
      shading: isHead ? { fill: BLUE, type: ShadingType.CLEAR, color: 'auto' } : (o.fill || rowFill) ? { fill: o.fill || rowFill, type: ShadingType.CLEAR, color: 'auto' } : undefined,
      children: String(o.t ?? '').split('\n').map((line) => new Paragraph({ alignment: right ? AlignmentType.RIGHT : AlignmentType.LEFT, spacing: { after: 0, line: 264 },
        children: isHead ? [new TextRun({ text: line, bold: true, color: 'FFFFFF', size: 20 })] : runs(line, { size: 20, bold: o.bold }) })),
    })
  }
  return [new Table({
    width: { size: W, type: WidthType.DXA }, columnWidths: widths,
    rows: [new TableRow({ tableHeader: true, children: head.map((h, i) => mk(h, i, true)) }),
      ...rows.map((r) => new TableRow({ children: r.cells ? r.cells.map((c, i) => mk(c, i, false, r.fill)) : r.map((c, i) => mk(c, i, false)) }))],
  }), new Paragraph({ spacing: { after: 120 }, children: [] })]
}

// ---------- số liệu ----------
const pr = meta.profile, mv = meta.models_valid, mt = meta.models_test, best = meta.best_model
const w = meta.weights, th = meta.thresholds, lv = meta.levels_test, lv4 = meta.levels_test_v4, lvv = meta.levels_valid
const kd = meta.kmeans_days, kdet = meta.kmeans_detectors
const TYPE = { WD: 'Ngày làm việc', SAT: 'Thứ Bảy', SUN: 'Chủ nhật / Lễ' }
const DAYNOTE = { '2015-02-12': 'Schmutziger Donnerstag — mở màn Fasnacht Luzern', '2015-02-13': 'Fasnacht', '2015-02-16': 'Güdismontag (Fasnacht)', '2015-02-17': 'Güdisdienstag (Fasnacht)', '2015-05-15': 'Ngày cầu sau lễ Thăng Thiên' }
const LBL = { dt: 'Decision Tree (CART, entropy)', nb: 'Naive Bayes (Gaussian)', mlp: 'Neural Network (MLP 32-16, tanh)', gb: 'Gradient Boosting (tập hợp cây quyết định)', persistence: 'Mốc: Persistence', rule_v4: 'Mốc: điểm luật v4 (C1–C4)' }
const bestLbl = LBL[best]
const tiers = pr.tiers
const nAct = pr.detectors - tiers.X
const fi = meta.feature_importance
const sc = meta.spatial_corr
const imp = (k) => (fi.find((f) => f.feature === k) || {}).importance || 0

// ---------- nội dung ----------
const C = []
// Trang bìa
C.push(new Paragraph({ spacing: { before: 2600 }, alignment: AlignmentType.CENTER, children: [new TextRun({ text: 'TÀI LIỆU THIẾT KẾ', bold: true, color: BLUE, size: 28 })] }))
C.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 120 }, children: [new TextRun({ text: 'Hệ thống hỗ trợ ra quyết định (DSS)', bold: true, size: 40 })] }))
C.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 400 }, children: [new TextRun({ text: 'Ưu tiên theo dõi & điều phối giao thông đô thị — Luzern (nguồn dữ liệu UTD19)', italics: true, color: '595959' })] }))
C.push(new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: 'Phần việc phụ trách: Vinh', bold: true })] }))
;['Bước 1 — Xác định bài toán DSS, đối tượng ra quyết định, input/output, ý tưởng giao diện',
  'Bước 2 — Thiết kế DSS model: tiêu chí đánh giá, kỹ thuật học máy, Priority Score, weights/thresholds',
  'Bước 3 — Kiến trúc hiện thực (engine, backend, frontend) và đánh giá'].forEach((t) => C.push(new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: t, size: 20 })] })))
C.push(new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: 'Giai đoạn 1 — Phiên bản 5.1 (DSS đọc từ DW, mô hình quyết định, goal seeking, năng lực ca trực)', color: '808080', size: 20 })] }))
C.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 600 }, children: [new TextRun({ text: 'Cập nhật lần cuối: 02/11/2026', color: '808080', size: 18 })] }))
C.push(brk())
C.push(new Paragraph({ children: [new TextRun({ text: 'Mục lục', bold: true, size: 32, color: BLUE })] }))
C.push(new TableOfContents('Mục lục', { hyperlink: true, headingStyleRange: '1-2' }))
C.push(P('(Nếu mục lục trống: mở bằng Word, bấm chuột phải vào mục lục → Update Field.)', { run: { italics: true, color: '808080', size: 18 } }))
C.push(brk())

// ===== 0 =====
C.push(H1('0. Tổng quan'))
C.push(P(`Tài liệu này là phiên bản 5 của thiết kế giai đoạn 1 cho phần việc DSS. Sau khi nhận bàn giao Data Warehouse, nguồn dữ liệu chuyển từ Toronto sang **Luzern (Thụy Sĩ)**, giai đoạn **${dmy(pr.first_day)} – ${dmy(pr.last_day)}** (nhóm cắt nửa đầu năm 2015 từ bộ 1 năm để vừa khả năng xử lý). Phiên bản này giữ khung bài toán của v4 nhưng thay engine chỉ dùng trọng số bằng một engine kết hợp **luật đa tiêu chí + học máy**, theo các kỹ thuật của Chương 5 (Decision Tree, Naive Bayes, Neural Network, K-means).`))
C.push(P('Mọi số liệu trong tài liệu được lấy từ lần chạy engine trên bảng khung 15 phút của DW (Phụ lục A, B, C). Các phiên bản trước dựa trên PeMS (v1), Hamburg (v2, v3) và Toronto (v4) không còn áp dụng. UTD19 do IVT, ETH Zürich công bố (Loder et al., 2019).'))

C.push(H2('0.1. Nguồn dữ liệu và phạm vi'))
C.push(...box('Phạm vi dữ liệu (xác định từ profiling)', [
  `Trung tâm Luzern; ${pr.detectors} detector có số đo (vùng khoảng 2,3 km × 3,2 km), trong đó ${nAct} detector còn hoạt động đến cuối giai đoạn lịch sử.`,
  `${pr.days} ngày liên tục ${dmy(pr.first_day)} – ${dmy(pr.last_day)}: ${pr.day_type_counts.WD} ngày làm việc, ${pr.day_type_counts.SAT} thứ Bảy, ${pr.day_type_counts.SUN} Chủ nhật/lễ (7 ngày lễ của bang Luzern).`,
  `Chu kỳ đo gốc 3 phút; DW gộp thành khung 15 phút (5 khoảng đo/khung, 96 khung/ngày): ${vn(pr.rows)} dòng.`,
  'Thước đo: flow (xe/giờ/làn) và occ (occupancy, miền 0–1). Cột speed trong UTD19 Luzern không có giá trị nên không dùng.',
  `Cột error có giá trị ở ${vn(pr.error_rows_pct, 2)}% số khoảng đo; trung vị theo detector ${vn(pr.error_median, 1)}%. Lỗi tập trung về đêm (00–05 giờ: 32–46% khoảng đo của detector tier A; ban ngày khoảng 3%).`,
  'Có giá trị sentinel trong khoảng đo lỗi (occ = 999,99; flow = 99.999), 4 detector kẹt (occ = 1, flow = 0 liên tục) và 11 detector nhóm ig11FD205 ngừng gửi dữ liệu từ 19–27/03/2015.',
  'Không có sự cố giao thông hay trạng thái đèn tín hiệu. Thời tiết theo ngày được bổ sung từ nguồn ngoài Open-Meteo vào DW (dw.dim_weather) để phân tích; DSS chưa dùng làm đầu vào (mục 2.7).',
]))

C.push(H2('0.2. Thay đổi so với phiên bản 4'))
C.push(...table(['Hạng mục', 'Phiên bản 4 (Toronto)', 'Phiên bản 5 (Luzern)'], [
  ['Dữ liệu', '188 detector, 61 ngày ở hai khối khác mùa, chu kỳ 15 phút', `${pr.detectors} detector, ${pr.days} ngày liên tục, chu kỳ 3 phút gộp 15 phút`],
  ['Hướng bài toán', 'Chỉ đối chiếu khung hiện tại với baseline (không dự báo vì dữ liệu ngắn)', 'Đối chiếu hiện tại + dự báo nguy cơ 30 phút tới bằng học máy (đủ 151 ngày lịch sử để huấn luyện)'],
  ['Loại ngày cho baseline', 'Gán tay: Ngày thường / Cuối tuần', 'K-means phân cụm ngày → 3 loại (Làm việc / Thứ Bảy / CN-lễ); phát hiện ngày đặc biệt'],
  ['Tiêu chí', 'C1–C4', `C1–C4 + C5 = xác suất ùn tắc bất thường trong 30 phút tới (${bestLbl})`],
  ['Trọng số, ngưỡng', 'Ước lượng theo kinh nghiệm (0,45/0,20/0,25/0,10; 70/40)', 'Tối ưu bằng tìm kiếm lưới trên tập kiểm định; ngưỡng Cao/Trung bình chọn theo F1/F2 trên tập kiểm định'],
  ['Độ chắc chắn', 'Chỉ có độ tin cậy dữ liệu (theo tier)', 'Tách hai khái niệm: chất lượng dữ liệu (tier) và độ chắc chắn của khuyến nghị (xác suất đã hiệu chỉnh)'],
  ['Kiểm định', 'Leave-one-out trong cùng giai đoạn', 'Chia theo thời gian: huấn luyện T1–T4, kiểm định T5, kiểm thử/phát lại T6'],
  ['Chất lượng dữ liệu', 'Tier A/B/C', 'Tier A/B/C + nhóm X (cảm biến kẹt, ngừng gửi dữ liệu) → gợi ý bảo trì'],
  ['Gợi ý hành động', '1 câu theo mức ưu tiên', 'Bảng quyết định theo mức + yếu tố chính (cảnh báo sớm, ùn kéo dài, ùn lan khu vực, nghi sự cố…)'],
], [2, 3.5, 4.5]))

C.push(H2('0.3. Mức độ phù hợp của dữ liệu với bài toán DSS'))
C.push(...table(['Hạng mục', 'DSS cần', 'Dữ liệu Luzern', 'Đánh giá và cách xử lý'], [
  ['Baseline lịch sử', 'So với cùng loại ngày, cùng khung giờ', `${pr.days} ngày liên tục; mỗi loại ngày đủ mẫu (≥ 21 ngày)`, '**Phù hợp.** Baseline theo loại ngày (K-means) × 96 khung, chuẩn hóa mức chung toàn thành phố.'],
  ['Học máy', 'Tập huấn luyện/kiểm định tách biệt theo thời gian', '120 ngày huấn luyện, 31 ngày kiểm định, 30 ngày kiểm thử', '**Phù hợp.** Đủ để huấn luyện và chọn mô hình dự báo ngắn hạn.'],
  ['Chỉ báo ùn tắc', 'Mức suy giảm tốc độ', 'Không có speed; có flow và occ', '**Phù hợp một phần.** Occupancy là chỉ báo chính, flow bổ sung.'],
  ['Đơn vị ưu tiên', 'Nhiều cảm biến để xếp hạng', `${pr.detectors} detector, ${tiers.A} tier A`, '**Phù hợp.** Xếp hạng toàn bộ, hiển thị top 10.'],
  ['Quan hệ không gian', 'Mức lan tỏa từ lân cận', 'Có tọa độ cho mọi detector; nhiều detector là các làn cùng điểm đo', `**Phù hợp một phần.** Tương quan về ~0 từ 0,5 km (Phụ lục A.3) nên C4 dùng bán kính 0,5 km, trọng số nhỏ.`],
  ['Độ tin cậy', 'Dữ liệu đo đáng tin', 'Lỗi về đêm cao, có sentinel, detector kẹt/ngừng gửi', '**Phù hợp một phần.** Luật DQ + tier A/B/C/X, độ tin cậy hiển thị riêng.'],
  ['Thời tiết, sự cố', 'Giải thích nguyên nhân', 'Sự cố: không có. Thời tiết: chỉ theo ngày (Open-Meteo, nguồn ngoài)', '**Không phù hợp.** DSS chỉ phát hiện và dự báo bất thường; thời tiết ngày quá thô so với khung 15 phút (thử nghiệm ở mục 2.7).'],
], [1.6, 2, 2.6, 3.8]))

C.push(H2('0.4. Chia dữ liệu theo thời gian và cách chạy "live"'))
C.push(P('Câu hỏi đặt ra khi bàn giao: dữ liệu gốc có 1 năm nhưng nhóm chỉ nạp 6 tháng đầu vào DW; khi "chạy thật" có cần lấy nửa năm còn lại để chạy live không? Phương án được chọn là **không nạp thêm, mà tách phần cuối của chính 6 tháng đã có làm luồng live**:'))
C.push(...table(['Giai đoạn', 'Thời gian', 'Vai trò'], [
  ['Huấn luyện', `${dmy(meta.split.train[0])} – ${dmy(meta.split.train[1])} (120 ngày)`, 'K-means, baseline, huấn luyện DT / NB / MLP / GB'],
  ['Kiểm định', `${dmy(meta.split.valid[0])} – ${dmy(meta.split.valid[1])} (31 ngày)`, 'Chọn mô hình, tối ưu trọng số, hiệu chỉnh ngưỡng'],
  ['Phát lại live (kiểm thử)', `${dmy(meta.split.replay[0])} – ${dmy(meta.split.replay[1])} (30 ngày)`, 'Mô hình huấn luyện lại trên 01/01–31/05; dữ liệu tháng 6 được "gửi tới" từng khung 15 phút như cảm biến thật; đo kết quả ngoài mẫu'],
], [2, 3, 5]))
C.push(...box('Lý do chọn phương án này', [
  'Đúng nguyên tắc vận hành: tại mỗi khung, engine chỉ thấy dữ liệu quá khứ (baseline, mô hình, tier đều dựng từ dữ liệu trước 01/06), nên kết quả tháng 6 là kiểm thử ngoài mẫu thật sự, không rò rỉ tương lai.',
  'Không phải xử lý lại tệp gốc (phần lý do nhóm đã cắt dữ liệu) và không thay đổi phạm vi DW đã bàn giao.',
  'Tháng 7–8 là kỳ nghỉ hè ở Thụy Sĩ, hồ sơ giao thông khác hẳn T1–T6; đưa vào live ngay sẽ khiến baseline lệch hàng loạt và cảnh báo giả tăng (bài học kiểm thử khác mùa ở v4).',
  'Hệ thống vẫn sẵn sàng cho dữ liệu mới: API có cổng nạp ngoài (POST /api/ingest) nhận từng khung 15 phút cùng cấu trúc mart.dss_detector_window. Khi muốn chạy với nửa cuối năm, nạp vào DW, chạy lại bước build (K-means sẽ xác định lại loại ngày mùa hè) rồi phát lại hoặc đẩy qua cổng nạp.',
], 'E2EFDA', '70AD47'))

// ===== 1 =====
C.push(H2('0.5. Cập nhật phiên bản 5.1 (02/11/2026)'))
C.push(P('Sau khi rà soát theo nội dung Chương 2–8 và yêu cầu bài tập lớn, phiên bản 5.1 bổ sung các điểm sau (engine, tiêu chí và mô hình C5 giữ nguyên):'))
C.push(...table(['Hạng mục', 'Trước', 'Phiên bản 5.1'], [
  ['Nguồn dữ liệu của DSS', 'Đọc thẳng tệp CSV khung 15 phút khi máy không có DW', 'Luôn đọc từ DW: mart.dss_detector_window (từ fact tổng hợp dw.fact_traffic_15min) và dw.dim_detector; CSV chỉ là phương án dự phòng. Kết quả trùng khớp đến độ chính xác float32.'],
  ['Rò rỉ thông tin ở giai đoạn kiểm định', 'Tier dữ liệu, cụm detector K-means, ma trận lân cận tính trên T1–T5 rồi dùng cả khi chọn mô hình trên T5', 'Giai đoạn kiểm định dựng lưới riêng chỉ dùng lịch sử T1–T4; giai đoạn cuối dùng T1–T5'],
  ['Năng lực ca trực', 'Không giới hạn số cảnh báo Cao (giờ cao điểm có khung trên 20)', `Tối đa ${th.max_high || '—'} cảnh báo Cao mỗi khung; phần vượt chuyển vào hàng chờ (mục 2.4)`],
  ['Goal seeking', 'Chỉ có what-if và phân tích độ nhạy', 'Đặt mục tiêu precision / recall / số cảnh báo → DSS tìm ngưỡng (mục 2.4)'],
  ['Mô hình quyết định', 'Chỉ mô tả tiêu chí và công thức', 'Phân loại bài toán, biến quyết định / không kiểm soát / kết quả, sơ đồ ảnh hưởng (mục 1.5); kiến trúc 4 phân hệ và phân loại DSS (mục 3.1)'],
  ['Nguồn ngoài', 'Không có', 'Thời tiết theo ngày (Open-Meteo) trong dw.dim_weather; đã thử làm đặc trưng cho C5 (mục 2.7)'],
], [2.3, 3.4, 4.3]))

C.push(H1('1. Xác định bài toán DSS'))
C.push(H2('1.1. Vấn đề ra quyết định (Decision Problem)'))
C.push(...box('Decision Problem Statement', [
  `Trong ${nAct} detector đang hoạt động ở trung tâm Luzern, tại mỗi khung 15 phút, detector/đoạn đường nào cần được ưu tiên theo dõi hoặc can thiệp trước — dựa trên mức occupancy vượt baseline cùng loại ngày và khung giờ, mức bất thường của lưu lượng, độ kéo dài của bất thường, ảnh hưởng từ detector lân cận, và **nguy cơ xảy ra ùn tắc bất thường trong 30 phút tới** do mô hình học máy dự báo?`,
]))
C.push(P('So với v4, hướng tiếp cận chuyển từ "chỉ so sánh" sang "so sánh + cảnh báo sớm", vì dữ liệu Luzern đủ dài và liên tục để huấn luyện mô hình dự báo ngắn hạn:'))
C.push(...table(['Tiêu chí so sánh', 'v4: Ưu tiên theo khung hiện tại', 'v5: Hiện tại + cảnh báo sớm 30 phút'], [
  ['Bản chất', 'Đối chiếu khung hiện tại với baseline', 'Đối chiếu + dự báo xác suất sự kiện ở 2 khung kế tiếp'],
  ['Dữ liệu cần', 'Baseline theo loại ngày × khung', 'Thêm tập huấn luyện/kiểm định tách biệt theo thời gian'],
  ['Khả thi', 'Cao', `Cao với Luzern: ${vn(meta.train_rows)} mẫu huấn luyện, ${vn(meta.valid_rows)} mẫu kiểm định`],
  ['Giá trị thêm', '—', `Bắt được sự kiện sắp khởi phát mà khung hiện tại chưa bất thường (${pc(mt[best].onset_share, 0)} số sự kiện tháng 6 thuộc loại này)`],
  ['Rủi ro', 'Thấp', 'Cảnh báo giả khi dự báo sai → kiểm soát bằng ngưỡng hiệu chỉnh theo precision và hiển thị độ tin cậy'],
], [2, 3.5, 4.5]))
C.push(H3('Các mức thời gian trong hệ thống'))
C.push(...table(['Mức thời gian', 'Giá trị', 'Giải thích'], [
  ['Grain của fact (DW)', '1 detector × 1 khoảng đo 3 phút', 'Giữ nguyên chu kỳ gốc của UTD19 Luzern'],
  ['Khung đánh giá DSS', '15 phút (5 khoảng đo)', 'Mart dss_detector_window gộp từ fact; cần ≥ 3/5 khoảng đo hợp lệ'],
  ['Chu kỳ làm mới dashboard', '15 phút (phát lại tháng 6)', 'Mặc định 3 giây thực = 1 khung; có thể bước, tua, nhảy tới khung bất kỳ'],
  ['Slot baseline', '3 loại ngày × 96 khung', 'Loại ngày từ K-means (mục 2.2.1); loại 5 ngày đặc biệt khỏi baseline'],
  ['Cửa sổ kéo dài (C3)', '4 khung gần nhất (1 giờ)', 'Bất thường duy trì hay thoáng qua'],
  ['Tầm dự báo (C5)', '2 khung kế tiếp (30 phút)', 'Đủ thời gian chuẩn bị điều chỉnh pha đèn / điều phối hiện trường'],
], [2.3, 2.7, 5]))

C.push(H2('1.2. Đối tượng ra quyết định'))
C.push(...table(['Thuộc tính', 'Mô tả'], [
  ['Đối tượng sử dụng', 'Nhân viên điều hành tại trung tâm quản lý giao thông đô thị (traffic control operator), trực theo ca.'],
  ['Quyết định cần đưa ra', `Trong ${nAct} detector, chọn top N đoạn đường cần ưu tiên theo dõi hoặc xử lý trong khung hiện tại và 30 phút tới (kiểm tra hiện trường, điều chỉnh tín hiệu, thông báo VMS, xác minh thiết bị).`],
  ['Loại quyết định', 'Bán cấu trúc (semi-structured): DSS xếp hạng và gợi ý, người vận hành quyết định cuối cùng (chấp nhận / điều chỉnh / bỏ qua).'],
  ['Tần suất cập nhật', 'Mỗi 15 phút.'],
  ['Bối cảnh sử dụng', 'Dashboard hỗ trợ lập kế hoạch vận hành, không điều khiển tự động. Trong đồ án, tháng 6/2015 được phát lại theo từng khung để mô phỏng vận hành.'],
], [2.5, 7.5]))
C.push(H3('Hỗ trợ theo các giai đoạn ra quyết định (Simon)'))
C.push(...table(['Giai đoạn', 'DSS hỗ trợ', 'Thành phần'], [
  ['Intelligence', 'Phát hiện bất thường hiện tại so với lịch sử', 'DW, baseline theo loại ngày (K-means), C1–C4'],
  ['Design', 'Dự báo nguy cơ và sinh phương án hành động', `${bestLbl} (C5), bảng quyết định (mục 2.5)`],
  ['Choice', 'Xếp hạng, phân mức, đề xuất top 10 trong giới hạn năng lực ca trực', 'Priority Score với trọng số tối ưu, ngưỡng hiệu chỉnh, tối đa N cảnh báo Cao/khung; goal seeking'],
  ['Implementation', 'Ghi nhận quyết định của người vận hành', 'Hộp thoại xác nhận, bảng dss.action_log'],
  ['Evaluation', 'Đối chiếu sự kiện thực tế sau 30 phút', 'Trang Cảnh báo: precision/recall trực tiếp; trang What-if & goal seeking'],
], [2, 4.5, 3.5]))

C.push(H2('1.3. Input / Output'))
C.push(H3('Input'))
C.push(...table(['Trường dữ liệu', 'Nguồn', 'Ghi chú'], [
  ['detid, road, fclass, linkid, pos, limit', 'dw.dim_detector ⋈ dw.dim_road_class (DW)', 'Hiển thị, lọc, đặc trưng loại đường cho mô hình'],
  ['long, lat', 'Hồ sơ vị trí detector', 'Khoảng cách haversine (C4), bản đồ'],
  ['n, n_err, n_occ_clean, mean_occ_*, mean_flow_*', 'mart.dss_detector_window (DW)', 'Tính từ fact tổng hợp dw.fact_traffic_15min (trung bình = tổng / số đếm); *_clean bỏ khoảng đo error'],
  ['data_tier (A/B/C/X)', 'Tính từ lịch sử', 'Tỷ lệ khoảng đo error; X: kẹt hoặc ngừng gửi'],
  ['day_type', 'Lịch + K-means', 'Làm việc / Thứ Bảy / CN-lễ; danh sách ngày lễ biết trước'],
  ['baseline μ, σ', 'Lịch sử theo loại ngày × khung × detector', `Tối thiểu ${8} mẫu; sàn σ; loại ngày đặc biệt`],
  ['city_factor', 'Tính tại khung', 'Trung vị (giá trị / baseline) trên detector tier A, cần ≥ 30 detector'],
  ['neighbor_weights', 'Từ long, lat', 'Gaussian, 50 m ≤ d ≤ 0,5 km, σ = 0,3 km'],
  ['Mô hình C5, cụm detector', 'Artifacts của bước build', 'model.joblib, detector_info.csv'],
], [3.2, 3, 3.8]))
C.push(H3('Output'))
C.push(...table(['Trường dữ liệu', 'Mô tả'], [
  ['detid, road, window_start', 'Detector, tên đường, thời điểm bắt đầu khung 15 phút'],
  ['priority_score', 'Điểm ưu tiên 0–100 (mục 2.3)'],
  ['priority_level', 'Cao / Trung bình / Thấp / Không đủ dữ liệu (mục 2.4)'],
  ['C1 … C5, p_event30', 'Điểm từng tiêu chí và xác suất sự kiện trong 30 phút tới'],
  ['top_factor', 'Tiêu chí đóng góp lớn nhất (w×C)'],
  ['suggested_action', 'Gợi ý hành động từ bảng quyết định (mục 2.5)'],
  ['certainty', 'Độ chắc chắn của khuyến nghị: xác suất (đã hiệu chỉnh) detector thật sự cần chú ý ở mức điểm này (mục 2.4)'],
  ['data_confidence, data_tier', 'Chất lượng dữ liệu (Cao / Trung bình / Thấp / Rất thấp) và tier — khác với độ chắc chắn'],
  ['explain', 'Đường đi trên cây quyết định giải thích lý do có nguy cơ'],
], [3, 7]))

C.push(H2('1.4. Giao diện (phát triển từ bản Figma)'))
C.push(P('Bản Figma nền tối được giữ bố cục (thanh bên, thanh lọc, 3 thẻ tổng quan, bản đồ trái – hàng đợi phải, trang danh sách detector) và chuyển sang **nền sáng**: nền xám-xanh nhạt, thẻ trắng, nhãn chữ mono in hoa, điểm nhấn xanh bạc hà; màu mức ưu tiên đỏ / hổ phách / xanh. Bản đồ dùng nền OpenStreetMap sáng (CARTO Positron) thay cho bản vẽ minh họa.'))
C.push(...table(['Màn hình / khối', 'Chức năng'], [
  ['Tổng quan', 'Thanh lọc (loại đường, mức, tier) + điều khiển phát lại (phát/dừng, +15′, +1 giờ, tốc độ, nhảy tới khung); 3 thẻ Cao/TB/Thấp có chênh lệch so với 15 phút trước; bản đồ; hàng đợi top 10; dải 96 khung trong ngày (bấm để xem lại); sơ đồ 5 giai đoạn Simon.'],
  ['Bản đồ', 'Toàn màn hình; tô màu theo mức ưu tiên hoặc theo cụm K-means; xòe các làn cùng điểm đo.'],
  ['Danh sách detector', 'Bảng đủ 158 detector: điểm, mức, occ/flow so với kỳ vọng, trạng thái (Live / Thiếu số đo / Offline), yếu tố chính, hành động, tin cậy, cụm; tìm kiếm, lọc, xuất CSV.'],
  ['Chi tiết detector', 'Vòng điểm, mức, độ tin cậy, P(ùn 30′); gợi ý hành động và nút ghi nhận; phân rã C1–C5; biểu đồ occupancy/flow so với kỳ vọng ±1σ; điểm theo khung; luật cây quyết định; lân cận C4.'],
  ['Cảnh báo & nhật ký', 'Danh sách cảnh báo Cao; nhật ký hành động với kết quả sau 30 phút; so sánh chất lượng cảnh báo v5 và v4 trên các khung đã phát lại.'],
  ['Mô hình học máy', 'So sánh DT / NB / MLP / GB / mốc; đường hiệu chỉnh điểm → xác suất; PR-AUC kiểm định và kiểm thử; quét độ sâu cây; tầm quan trọng đặc trưng; K-means ngày và detector; tương quan không gian.'],
  ['Trọng số, What-if & goal seeking', 'Thanh trượt trọng số, ngưỡng và năng lực ca trực; xem ngay thay đổi xếp hạng, số cảnh báo và chỉ số đánh giá; goal seeking: nhập mục tiêu precision / recall / số cảnh báo tối đa → hệ thống tìm ngưỡng; áp dụng cho hệ thống; bảng top trọng số và phân tích độ nhạy.'],
  ['Mô hình quyết định & kiến trúc', 'Phát biểu bài toán, biến quyết định / không kiểm soát / kết quả, sơ đồ ảnh hưởng, 4 phân hệ DSS, phân loại DSS, bảng quyết định (mục 1.5, 3.1).'],
  ['Kho dữ liệu & ETL', 'Chỉ đọc: chế độ nạp, đối soát RC-A…RC-E, dòng bị cách ly, độ phủ theo tháng, lược đồ sao, kho siêu dữ liệu, nhật ký ETL — để người dùng biết DSS đang dựa trên dữ liệu nào.'],
], [2.3, 7.7]))
C.push(P('Ghi chú thiết kế: độ tin cậy dữ liệu luôn hiển thị cạnh điểm số; detector nhóm X hiển thị màu xám đậm và gợi ý bảo trì thay vì điểm.'))


C.push(H2('1.5. Mô hình quyết định (Chương 5, 7)'))
C.push(P('DSS thực hiện phân tích trên **mô hình của hệ thống giao thông** chứ không trên hệ thống thật: mô hình gồm baseline thống kê, các tiêu chí C1–C5, mô hình học máy và bảng quyết định. Theo cách phân loại của Chương 7:'))
C.push(...table(['Khía cạnh', 'Phân loại', 'Giải thích'], [
  ['Cấu trúc bài toán', 'Bán cấu trúc, lặp lại', 'Phát hiện bất thường có luật rõ (lập trình được); dự báo và chọn hành động cần phán đoán của người vận hành.'],
  ['Mô hình tĩnh / động', 'Động (dynamic)', 'Trạng thái thay đổi theo từng khung 15 phút; dùng đặc trưng trễ t−1…t−3 và dự báo 2 khung kế tiếp.'],
  ['Mức chắc chắn', 'Quyết định trong điều kiện rủi ro', `Kết quả không chắc chắn nhưng ước lượng được xác suất: C5 = P(sự kiện trong 30 phút), độ chắc chắn hiệu chỉnh isotonic (mục 2.4). Không phải "bất định" vì xác suất được đo trên lịch sử.`],
  ['Nguyên tắc lựa chọn', 'Tối ưu có ràng buộc', `Chọn trọng số tối đa precision@10; ngưỡng Cao/Trung bình theo F1/F2; ràng buộc năng lực ca trực tối đa ${th.max_high || '—'} cảnh báo Cao mỗi khung. Có thể chuyển sang thỏa mãn mục tiêu (goal seeking).`],
  ['Phương pháp tìm kiếm', 'Liệt kê đầy đủ (blind search, complete enumeration)', 'Lưới trọng số bước 0,05 thỏa Σw = 1 được duyệt hết; ngưỡng quét bước 1–5 điểm.'],
], [2.2, 2.6, 5.2]))
C.push(H3('Thành phần mô hình: biến quyết định, biến không kiểm soát, biến kết quả'))
C.push(...table(['Loại biến', 'Trong DSS', 'Ai / cái gì xác định'], [
  [{ t: 'Biến quyết định', bold: true }, `Trọng số w₁…w₅ (đang dùng ${['C1', 'C2', 'C3', 'C4', 'C5'].map((k) => vn(w[k], 2)).join(' / ')}); ngưỡng Cao ${th.high}, Trung bình ${th.medium}; năng lực ca trực N = ${th.max_high || '∞'}; hành động cho từng cảnh báo (chấp nhận / điều chỉnh / bỏ qua)`, 'Tối ưu trên tháng 5, người vận hành có thể chỉnh (what-if, goal seeking)'],
  [{ t: 'Biến không kiểm soát', bold: true }, 'Occupancy, lưu lượng mỗi khung; loại ngày, ngày lễ, sự kiện đặc biệt (Fasnacht); lỗi cảm biến; sự cố, công trình, thời tiết (chưa quan sát trực tiếp)', 'Môi trường giao thông và thiết bị đo'],
  [{ t: 'Biến trung gian', bold: true }, 'Baseline μ, σ; z occupancy / flow; C1–C5; Priority Score; mức ưu tiên', 'Mô hình tính từ hai nhóm trên'],
  [{ t: 'Biến kết quả', bold: true }, 'Precision / recall của mức Cao (tách đang diễn ra / sắp xảy ra); precision@10; số cảnh báo mỗi khung (khối lượng việc); số sự kiện bị bỏ sót', 'Đo khi đối chiếu sự kiện thực tế sau 30 phút'],
], [2, 5.4, 2.6]))
C.push(H3('Sơ đồ ảnh hưởng (influence diagram)'))
if (fs.existsSync(IMG_INFLUENCE)) {
  C.push(new Paragraph({ alignment: AlignmentType.CENTER, children: [new ImageRun({ type: 'png', data: fs.readFileSync(IMG_INFLUENCE), transformation: { width: 620, height: 155 } })] }))
  C.push(P('Hình chữ nhật viền xanh lá: biến quyết định; nền cam: biến không kiểm soát; nền xám: biến trung gian; nền xanh dương: biến kết quả. Bảng quyết định còn dùng trực tiếp C1, C3, z lưu lượng và tier để chọn loại hành động (lược bớt mũi tên cho dễ đọc).', { run: { italics: true, color: '595959', size: 18 } }))
} else {
  C.push(P('Occupancy, lưu lượng → z → C1–C4; loại ngày → baseline → z; z, tier, loại ngày → C5 (ML); C1–C5 và trọng số → Priority Score; Priority Score và ngưỡng, năng lực ca trực → mức ưu tiên → hành động (bảng quyết định) → precision/recall, số cảnh báo, sự kiện bị bỏ sót.'))
}

// ===== 2 =====
C.push(H1('2. Thiết kế DSS model'))
C.push(P('Model gồm ba lớp: (1) **học không giám sát** (K-means) để xác định loại ngày cho baseline và nhóm hành vi detector; (2) **tiêu chí luật** C1–C4 đo bất thường hiện tại; (3) **học có giám sát** cho C5 dự báo nguy cơ 30 phút. Năm tiêu chí được gộp thành Priority Score bằng trọng số tối ưu trên tập kiểm định.'))
C.push(H2('2.1. Tiêu chí đánh giá'))
C.push(...table(['Ký hiệu', 'Tiêu chí', 'Cách tính', 'Nguồn'], [
  ['C1', 'Occupancy vượt baseline', 'z₁ = (occ/f − μ_occ)/σ_occ với μ, σ cùng loại ngày, cùng khung; f là hệ số mức chung. Sàn σ = max(0,005; 10%·μ). C1 = min(max(z₁,0),3)/3 × 100', 'Mart khung 15 phút, baseline'],
  ['C2', 'Bất thường lưu lượng', 'z₂ = |flow/f − μ_flow|/σ_flow (cả tăng và giảm); sàn σ = max(10; 10%·μ). C2 = min(z₂,3)/3 × 100', 'Mart khung 15 phút, baseline'],
  ['C3', 'Độ kéo dài', '100 × số khung có C1 ≥ 50 trong 4 khung gần nhất (gồm khung hiện tại) / số khung hợp lệ (≥ 2)', 'C1 các khung trước'],
  ['C4', 'Lan tỏa từ lân cận', 'Σ wᵢⱼ·C1ⱼ / Σ wᵢⱼ, wᵢⱼ = exp(−d²/σd²) nếu 0,05 ≤ d ≤ 0,5 km; σd = 0,3 km; chỉ lân cận tier A, B', 'Tọa độ detector'],
  ['C5', 'Nguy cơ ùn tắc 30 phút tới (ML)', `C5 = min(P/0,5; 1) × 100, P là xác suất do ${bestLbl} dự báo sự kiện ở khung t+1 hoặc t+2 (mục 2.2.3)`, 'Đặc trưng từ C1–C4, lịch sử, cụm'],
], [0.8, 1.8, 5.4, 2]))
C.push(P('**Chuẩn hóa mức chung toàn thành phố.** Mỗi khung chia giá trị cho f = trung vị (giá trị / baseline) trên các detector tier A (cần ≥ 30 detector, giới hạn 0,5–2; thiếu thì f = 1). Điểm phản ánh bất thường cục bộ so với phần còn lại của thành phố cùng thời điểm; cái giá là bất thường đồng loạt toàn thành phố bị làm mờ.'))
C.push(P('**Sự kiện ùn tắc bất thường** (dùng làm nhãn học máy và để đánh giá): khung có z₁ ≥ 2 **và** occupancy cao hơn kỳ vọng ít nhất 5 điểm phần trăm. Điều kiện thứ hai loại các trường hợp z lớn nhưng occupancy vẫn rất thấp (ban đêm).'))

C.push(H2('2.2. Kỹ thuật học máy trong DSS'))
C.push(H3('2.2.1. K-means phân cụm ngày → loại ngày cho baseline'))
const ct = kd.crosstab
C.push(P(`Mỗi ngày lịch sử (01/01–31/05) được biểu diễn bằng vector 96 chiều: lưu lượng trung bình toàn thành phố theo khung 15 phút (detector tier A). Silhouette theo k: ${kd.scan.map((s) => `k=${s.k}: ${vn(s.silhouette, 3)}`).join('; ')}. Chọn **k = 3** vì tách được Thứ Bảy khỏi Chủ nhật (k = 2 có silhouette cao hơn chút nhưng gộp hai loại có hồ sơ khác nhau). Kết quả: thứ 2–6 rơi gần như hoàn toàn vào cụm "Ngày làm việc", 100% thứ Bảy vào cụm "Thứ Bảy", 100% Chủ nhật vào cụm "Chủ nhật". Mọi ngày lễ của bang Luzern rơi vào cụm Chủ nhật — xác nhận quy tắc gán ngày lễ = Chủ nhật.`))
C.push(P(`K-means còn phát hiện **${kd.mismatch.length} ngày đặc biệt** không nằm trong lịch lễ: ${kd.mismatch.map((r) => `${dmy(r.day)} (${DAYNOTE[r.day] || ''} → ${TYPE[r.cluster]})`).join('; ')}. Các ngày này bị loại khỏi baseline để không làm lệch μ, σ.`))
C.push(H3('2.2.2. K-means phân cụm detector theo hành vi'))
C.push(P(`Mỗi detector được biểu diễn bằng hồ sơ occupancy 24 giờ của ngày làm việc, chuẩn hóa z theo từng detector (chỉ giữ hình dạng). Silhouette: ${kdet.scan.map((s) => `k=${s.k}: ${vn(s.silhouette, 3)} (${s.sizes.join('/')})`).join('; ')}. Từ k = 4 trở lên xuất hiện cụm chỉ 1 detector nên chọn **k = ${kdet.k}**: ${Object.entries(kdet.sizes).map(([k, v]) => `${k} (${v})`).join(', ')}. Cụm được dùng làm đặc trưng cho mô hình C5, để lọc/tô màu trên bản đồ, và giúp người vận hành hiểu bối cảnh (ví dụ cảnh báo buổi sáng ở detector "Đỉnh buổi chiều" là bất thường đáng chú ý hơn).`))
C.push(H3('2.2.3. Mô hình dự báo C5 (học có giám sát)'))
C.push(...table(['Thành phần', 'Thiết kế'], [
  ['Nhãn', `Y(t) = 1 nếu có sự kiện ùn tắc bất thường ở khung t+1 hoặc t+2. Tỷ lệ dương: huấn luyện ${pc(meta.pos_rate.train)}, kiểm định ${pc(meta.pos_rate.valid)}, kiểm thử ${pc(meta.pos_rate.test)} (mất cân bằng).`],
  ['Đặc trưng (≈ 30)', 'Hiện tại: occ, occ − μ, flow/μ, z_occ, z_flow, đang có sự kiện, C3, C4, hệ số mức chung, tỷ lệ khoảng đo lỗi. Trễ: z_occ ở t−1, t−2, t−3 và biến thiên. Bối cảnh: baseline tăng trong 30 phút tới (μ(t+2) − μ(t)), giờ (sin/cos), loại ngày. Tĩnh: occupancy TB, tier, loại đường, cụm K-means.'],
  ['Thuật toán so sánh', 'Decision Tree (CART, tiêu chí entropy/information gain, quét max_depth 4–12); Naive Bayes (Gaussian); Neural Network (MLP 2 lớp ẩn 32-16, tanh, Adam, early stopping); Gradient Boosting (HistGradientBoosting — mở rộng của Decision Tree: cộng dồn tối đa 400 cây nông, mỗi cây sửa phần sai của các cây trước, dừng sớm theo tập kiểm định nội bộ). Mốc không học: Persistence (Y dự báo = trạng thái hiện tại) và điểm luật v4.'],
  ['Huấn luyện', `${vn(meta.train_rows)} mẫu (lấy mẫu 600 nghìn cho DT/NB, 300 nghìn cho MLP), 01/01–30/04; bỏ 2 khung cuối để nhãn không chạm tháng 5.`],
  ['Chọn mô hình', 'PR-AUC (average precision) trên tháng 5 — phù hợp nhãn mất cân bằng; bổ sung ROC-AUC, F1, recall sự kiện mới khởi phát.'],
  ['Triển khai', 'Huấn luyện lại mô hình đã chọn trên 01/01–31/05, dùng cho phát lại tháng 6. Một cây quyết định độ sâu 6 được huấn luyện song song để giải thích (đường đi gốc → lá hiển thị trên giao diện).'],
], [2.2, 7.8]))
const order = ['dt', 'nb', 'mlp', 'gb', 'persistence', 'rule_v4']
C.push(...table(['Mô hình (tháng 5)', 'PR-AUC', 'ROC-AUC', 'Precision', 'Recall', 'F1', 'Recall sự kiện mới'],
  order.map((k) => ({ cells: [LBL[k], vn(mv[k].pr_auc, 3), vn(mv[k].roc_auc, 3), pc(mv[k].precision), pc(mv[k].recall), vn(mv[k].f1, 3), pc(mv[k].onset_recall)], fill: k === best ? 'E2EFDA' : undefined })),
  [3.4, 1.1, 1.1, 1.1, 1.1, 1, 1.4], { num: [1, 2, 3, 4, 5, 6] }))
C.push(P(`**Kết luận:** ${bestLbl} có PR-AUC cao nhất (${vn(mv[best].pr_auc, 3)}), gấp ${vn(mv[best].pr_auc / mv.persistence.pr_auc, 1)} lần Persistence và ${vn(mv[best].pr_auc / mv.rule_v4.pr_auc, 1)} lần điểm luật v4. Một cây quyết định đơn (độ sâu ${mv.dt.params.max_depth}) đạt ${vn(mv.dt.pr_auc, 3)}, Neural Network ${vn(mv.mlp.pr_auc, 3)}; Gradient Boosting cải thiện vì gộp nhiều cây giảm phương sai mà vẫn giữ khả năng bắt tương tác ngưỡng của cây. Một cây độ sâu 6 vẫn được huấn luyện song song làm cây giải thích trên giao diện. Naive Bayes kém nhất (${vn(mv.nb.pr_auc, 3)}) vì giả định độc lập bị vi phạm: các đặc trưng trễ của z-score tương quan rất mạnh. Mốc Persistence không thể dự báo sự kiện mới khởi phát (recall 0%), trong khi mô hình học máy bắt được ${pc(mv[best].onset_recall, 0)}. Kiểm thử ngoài mẫu tháng 6: PR-AUC ${vn(mt[best].pr_auc, 3)} (Persistence ${vn(mt.persistence.pr_auc, 3)}, v4 ${vn(mt.rule_v4.pr_auc, 3)}) — mức giảm nhẹ so với tháng 5 cho thấy mô hình không quá khớp.`))

C.push(H2('2.3. Công thức Priority Score'))
C.push(...formula(['Priority Score = w₁·C1 + w₂·C2 + w₃·C3 + w₄·C4 + w₅·C5'], '(thang điểm 0–100; Σwᵢ = 1)'))
C.push(P('Quy tắc thiếu dữ liệu: (1) C1 và C2 bắt buộc — khung không có số đo hợp lệ, baseline dưới 8 mẫu hoặc detector nhóm X thì không chấm, hiển thị "Không đủ dữ liệu"; (2) C3, C4, C5 thiếu thì bỏ và chuẩn hóa lại trọng số các tiêu chí còn lại; (3) detector không có lân cận hợp lệ thì bỏ C4.'))

C.push(H2('2.4. Trọng số và ngưỡng phân loại'))
C.push(P(`Trọng số được tìm bằng **tìm kiếm lưới** (bước 0,05; mỗi trọng số trong [0,05; 0,50] để mọi tiêu chí còn hiện diện và không tiêu chí nào chi phối quá nửa) trên tập kiểm định tháng 5. Hàm mục tiêu: **precision@10** — trung bình tỷ lệ detector trong top 10 mỗi khung thật sự cần chú ý (có sự kiện ngay tại khung hoặc trong 30 phút tới).`))
C.push(...table(['Tiêu chí', 'v4', 'v5 (tối ưu)', 'Giải thích'], [
  ['C1 — Occupancy vượt baseline', '0,45', vn(w.C1, 2), 'Vẫn là tín hiệu hiện tại mạnh nhất'],
  ['C2 — Bất thường lưu lượng', '0,20', vn(w.C2, 2), 'Chạm cận dưới: thông tin của flow đã nằm trong đặc trưng của C5'],
  ['C3 — Độ kéo dài', '0,25', vn(w.C3, 2), 'Chạm cận dưới: C5 đã dùng z trễ 3 khung'],
  ['C4 — Lan tỏa lân cận', '0,10', vn(w.C4, 2), 'Tương quan không gian yếu (≤ 0,21) nhưng có ích khi lân cận cùng bất thường'],
  ['C5 — Nguy cơ 30 phút (ML)', '—', vn(w.C5, 2), 'Chạm cận trên: dự báo đóng góp nhiều nhất vào việc chọn đúng'],
  [{ t: 'Precision@10 tháng 5 / tháng 6', bold: true }, `${pc(meta.p_at_10.valid_v4)} / ${pc(meta.p_at_10.test_v4)}`, `${pc(meta.p_at_10.valid_v5)} / ${pc(meta.p_at_10.test_v5)}`, 'Cùng tiêu chí C1–C5, chỉ khác trọng số'],
], [3, 1.3, 1.5, 4.2]))
C.push(P(`Phân tích độ nhạy (Phụ lục B): lệch mỗi trọng số ±0,05–0,10 làm precision@10 thay đổi dưới ${vn(Math.max(...meta.sensitivity.map((s) => Math.abs(s.p_at_10 - meta.p_at_10.valid_v5))) * 100, 1)} điểm %; 10 bộ trọng số tốt nhất đều có C5 = ${vn(Math.min(...meta.weights_top.map((r) => r.C5)), 2)} và C2 = 0,05, phần còn lại chia giữa C1, C3, C4 với precision@10 chênh nhau dưới ${vn((meta.weights_top[0].p_at_10 - meta.weights_top[meta.weights_top.length - 1].p_at_10) * 100, 2)} điểm % — kết luận chính (dự báo C5 chiếm nửa trọng số, C2 tối thiểu) ổn định, còn cách chia giữa C1/C3/C4 có thể điều chỉnh theo kinh nghiệm vận hành mà gần như không mất độ chính xác.`))
C.push(H3('Ngưỡng phân loại mức ưu tiên'))
const SW = meta.threshold_sweep_valid || []
const swRow = (t) => SW.find((r) => r.threshold === t) || {}
C.push(P(`Ngưỡng được **chọn trên tháng 5 bằng F-score**, với nhãn "cần chú ý" = có sự kiện ngay tại khung hoặc trong 30 phút sau. Mỗi ngưỡng t (bước 5) được xem như một bộ phân loại "điểm ≥ t", rồi đo precision, recall, F1 và F2:`))
C.push(B(`**Cao (cần hành động) = ngưỡng có F1 lớn nhất** — cân bằng giữa cảnh báo đúng và không bỏ sót, vì mỗi cảnh báo Cao tiêu tốn nguồn lực điều phối.`))
C.push(B(`**Trung bình (theo dõi) = ngưỡng thấp hơn có F2 lớn nhất** — F2 coi bỏ sót nặng gấp đôi cảnh báo thừa, phù hợp với mức chỉ yêu cầu theo dõi.`))
C.push(...table(['Ngưỡng', 'Cảnh báo/khung', 'Precision', 'Recall', 'Recall đang diễn ra', 'Recall sắp xảy ra', 'F1', 'F2'],
  SW.filter((r) => r.threshold >= 20 && r.threshold <= 60).map((r) => ({ cells: [String(r.threshold), vn(r.alerts_per_window, 1), pc(r.precision), pc(r.recall), pc(r.recall_now), pc(r.recall_future), vn(r.f1, 3), vn(r.f2, 3)],
    fill: r.threshold === th.high ? 'F8CBAD' : r.threshold === th.medium ? 'FFE699' : undefined })),
  [1.1, 1.4, 1.2, 1.1, 1.6, 1.6, 1, 1], { num: [1, 2, 3, 4, 5, 6, 7] }))
C.push(P(`Kết quả: **Cao ≥ ${th.high}**, **Trung bình ≥ ${th.medium}**. Ở ngưỡng Cao, tháng 5 đạt precision ${pc(swRow(th.high).precision)}, recall ${pc(swRow(th.high).recall)}, trong đó bắt ${pc(swRow(th.high).recall_now)} sự kiện **đang diễn ra** nhưng chỉ ${pc(swRow(th.high).recall_future)} sự kiện **sắp xảy ra**. Hạ ngưỡng thêm chủ yếu tăng phần sắp xảy ra nhưng precision giảm nhanh hơn (F1 giảm); nâng ngưỡng (ví dụ 55) cho precision khoảng 90% nhưng recall chỉ còn khoảng 1/3 — đó là lý do các phương án trước (ngưỡng 30 theo precision cộng dồn, ngưỡng 55 theo xác suất biên 60%) bị thay.`))
C.push(H3('Độ chắc chắn của khuyến nghị'))
C.push(P(`Ngoài mức, mỗi khuyến nghị kèm **độ chắc chắn** = P(cần chú ý | điểm) ước lượng bằng hồi quy isotonic trên tháng 5 (đơn điệu theo điểm):`))
C.push(...table(['Priority Score', ...[20, 25, 30, 35, 40, 50, 60, 70, 80].map(String)], [['P(cần chú ý)', ...[20, 25, 30, 35, 40, 50, 60, 70, 80].map((x) => pc(meta.certainty_curve[x], 0))]], [2.2, 1, 1, 1, 1, 1, 1, 1, 1, 1], { num: [1, 2, 3, 4, 5, 6, 7, 8, 9] }))
C.push(P(`Giá trị này được hiển thị là "Chắc chắn x%", tách khỏi **chất lượng dữ liệu** (tier A/B/C, số khoảng đo hợp lệ). Cảnh báo sát ngưỡng Cao có độ chắc chắn khoảng ${pc(meta.certainty_curve[th.high], 0)}; điểm từ 60 trở lên gần như chắc chắn. Xác suất 30–50% của riêng mô hình C5 không phải là "kém": tỷ lệ nền chỉ khoảng 3–4%, nên mức đó đã cao gấp khoảng 10 lần ngẫu nhiên.`))
C.push(...table(['Khoảng điểm', 'Mức ưu tiên', 'Ý nghĩa', 'Tỷ lệ khung T6', 'Precision T6'], [
  { cells: [`Score ≥ ${th.high}`, { t: 'Cao', bold: true }, 'Cần xử lý trong ca, theo bảng quyết định', pc(lv.dist['Cao'] / 100, 2), pc(lv.precision['Cao'])], fill: 'F8CBAD' },
  { cells: [`${th.medium} ≤ Score < ${th.high}`, { t: 'Trung bình', bold: true }, 'Theo dõi sát', pc(lv.dist['Trung bình'] / 100, 2), pc(lv.precision['Trung bình'])], fill: 'FFE699' },
  { cells: [`Score < ${th.medium}`, { t: 'Thấp', bold: true }, 'Hoạt động bình thường', pc(lv.dist['Thấp'] / 100, 2), pc(lv.precision['Thấp'])], fill: 'C6E0B4' },
  ['—', 'Không đủ dữ liệu', 'Thiếu số đo / nhóm X / baseline thiếu', pc(lv.dist['Không đủ dữ liệu'] / 100, 2), '—'],
], [2, 1.6, 3.4, 1.5, 1.5]))
C.push(P(`Tháng 6 (ngoài mẫu): trung bình ${vn(lv.high_per_window_mean, 2)} detector Cao mỗi khung (v4: ${vn(lv4.high_per_window_mean, 2)}); mức Cao đúng ${pc(lv.precision['Cao'])} và bắt ${pc(lv.event_recall_high)} số detector-khung cần chú ý (v4: ${pc(lv4.precision['Cao'])} và ${pc(lv4.event_recall_high)}), gồm ${pc(lv.recall_now_high)} sự kiện đang diễn ra và ${pc(lv.recall_future_high)} sự kiện sắp xảy ra; tính cả mức Trung bình bắt ${pc(lv.event_recall_high_med)}. Chi tiết ở chương 4.`))


C.push(H3('Năng lực ca trực (giới hạn số cảnh báo Cao mỗi khung)'))
{
  const su = strat('v5 không giới hạn'), s0 = EV ? EV.strategies[0] : null
  C.push(P(`Nếu không giới hạn, ngưỡng theo F1 cho trung bình ${su ? vn(su.high_per_window, 1) : '—'} cảnh báo Cao mỗi khung, nhưng giờ cao điểm có khung tới ${su ? su.high_per_window_max : '—'} cảnh báo — vượt khả năng xử lý của một ca trực. DSS v5.1 thêm **ràng buộc nguồn lực**: mỗi khung chỉ giữ **tối đa N = ${th.max_high || '—'}** detector điểm cao nhất ở mức Cao (N bằng top-K dùng khi tối ưu trọng số); detector còn lại có điểm ≥ ngưỡng Cao chuyển thành **hàng chờ** (mức Trung bình, mã QUEUE) để xử lý khi có người rảnh.`))
  if (su && s0) C.push(...table(['Cấu hình (tháng 6)', 'Cao/khung TB', 'Cao/khung tối đa', 'Precision Cao', 'Recall Cao', 'F1 Cao'], [
    { cells: [`Giới hạn N = ${th.max_high}`, vn(s0.high_per_window, 2), String(s0.high_per_window_max ?? '—'), pc(s0.precision_high), pc(s0.recall_high), vn(s0.f1_high, 3)], fill: 'E2EFDA' },
    ['Không giới hạn', vn(su.high_per_window, 2), String(su.high_per_window_max ?? '—'), pc(su.precision_high), pc(su.recall_high), vn(su.f1_high, 3)],
  ], [3, 1.4, 1.6, 1.4, 1.3, 1.1], { num: [1, 2, 3, 4, 5] }))
  if (EV && EV.capacity_sweep) {
    C.push(P('Quét N trên tháng 6 (cùng trọng số và ngưỡng) cho thấy rõ sự đánh đổi; N là **biến quyết định của người quản lý ca** (chỉnh được trên trang What-if), không phải tham số kỹ thuật:'))
    C.push(...table(['N (Cao/khung)', 'Cao/khung TB', 'Precision Cao', 'Recall Cao', 'Recall đang diễn ra', 'Recall sắp xảy ra', 'F1 Cao'],
      EV.capacity_sweep.map((r) => ({ cells: [r.max_high ? String(r.max_high) : 'Không giới hạn', vn(r.high_per_window, 2), pc(r.precision_high), pc(r.recall_high), pc(r.recall_now_high), pc(r.recall_future_high), vn(r.f1_high, 3)],
        fill: r.max_high === th.max_high ? 'E2EFDA' : undefined })), [1.8, 1.4, 1.4, 1.3, 1.6, 1.6, 1], { num: [1, 2, 3, 4, 5, 6] }))
    C.push(P('Giới hạn cắt bớt trước hết các cảnh báo "sắp xảy ra" (điểm thấp hơn cảnh báo đang ùn), nên recall dự báo giảm nhanh nhất. Với đội trực lớn hơn, nên tăng N.'))
  }
}
C.push(H3('Goal seeking'))
C.push(P('What-if trả lời "nếu đổi trọng số / ngưỡng thì kết quả ra sao". **Goal seeking** làm chiều ngược lại (Chương 7): người vận hành đặt **mục tiêu cho biến kết quả**, DSS tìm **giá trị biến quyết định** (ngưỡng Cao) thỏa mục tiêu, dựa trên đường cong precision / recall / số cảnh báo theo ngưỡng của tháng 5, rồi kiểm chứng trên các khung tháng 6 đã phát lại:'))
C.push(...table(['Mục tiêu', 'Quy tắc chọn ngưỡng', 'Ý nghĩa vận hành'], [
  ['Precision mức Cao ≥ x%', 'Ngưỡng **thấp nhất** đạt mục tiêu (giữ recall cao nhất)', 'Đội trực chỉ muốn nhận cảnh báo đúng ít nhất x%'],
  ['Recall mức Cao ≥ x%', 'Ngưỡng **cao nhất** vẫn đạt (giữ precision cao nhất)', 'Không được bỏ sót quá (100 − x)% sự kiện'],
  ['Số cảnh báo Cao ở 95% khung ≤ N', 'Ngưỡng **thấp nhất** đạt mục tiêu', 'Ràng buộc nhân lực, tính cả giờ cao điểm'],
], [2.6, 3.6, 3.8]))
C.push(P('Nếu không ngưỡng nào đạt, giao diện báo "không khả thi" — người vận hành phải nới mục tiêu hoặc đổi trọng số (đánh đổi precision ↔ recall).'))

C.push(H2('2.5. Bảng quyết định gợi ý hành động'))
C.push(...table(['Điều kiện (theo thứ tự ưu tiên)', 'Mã', 'Gợi ý hành động'], [
  ['Detector nhóm X', 'MAINT', 'Thiết bị cần bảo trì — không chấm điểm'],
  ['Điểm ≥ ngưỡng Cao nhưng ngoài top-N của khung', 'QUEUE', 'Hàng chờ: ca trực đã đủ số cảnh báo — xử lý khi có người rảnh'],
  ['Mức Thấp', 'NORMAL', 'Hoạt động bình thường'],
  ['Mức Trung bình và C5 ≥ 50', 'WATCH_RISK', 'Theo dõi sát — có nguy cơ ùn trong 30 phút tới'],
  ['Mức Trung bình', 'WATCH', 'Theo dõi sát, chưa cần can thiệp'],
  ['Cao, tier C', 'VERIFY', 'Xác minh bằng camera/thiết bị trước khi điều phối'],
  ['Cao, yếu tố chính C5 và C1 < 50', 'EARLY', 'Cảnh báo sớm: chuẩn bị kịch bản điều chỉnh pha đèn trong 15–30 phút'],
  ['Cao, C3 ≥ 75', 'PERSIST', 'Ùn kéo dài: điều phối hiện trường, thông báo VMS / gợi ý đường vòng'],
  ['Cao, yếu tố chính C4', 'AREA', 'Ùn lan theo khu vực: phối hợp tín hiệu các nút lân cận'],
  ['Cao, yếu tố chính C2, flow giảm, C1 ≥ 50', 'INCIDENT', 'Nghi sự cố chắn làn: kiểm tra camera'],
  ['Cao, yếu tố chính C2, flow tăng', 'SURGE', 'Lưu lượng tăng đột biến: tăng thời gian xanh cho hướng này'],
  ['Cao, còn lại', 'INTERVENE', 'Ưu tiên kiểm tra và can thiệp trong ca'],
], [3.6, 1.4, 5]))
C.push(P('Người vận hành có thể chấp nhận, điều chỉnh nội dung hoặc bỏ qua gợi ý; mọi quyết định được lưu (dss.action_log) và tự động đối chiếu với sự kiện thực tế sau 30 phút.'))

C.push(H2('2.6. Chính sách chất lượng dữ liệu và độ tin cậy'))
C.push(P(`Luật mức khung: khung 15 phút cần ≥ 3/5 khoảng đo hợp lệ; loại occ > 1, flow > 3.000 (sentinel), và occ ≥ 0,95 kèm flow = 0 (cảm biến kẹt); loại slot 96 (khoảng đo 86.400 s, ${vn(pr.dropped.slot_out_of_range)} dòng). Độ tin cậy là trường riêng, không trộn vào điểm.`))
C.push(...table(['Tier', 'Điều kiện', 'Số detector', 'Cách dùng dữ liệu', 'data_confidence'], [
  ['A', 'Lỗi ≤ 25% khoảng đo', String(tiers.A), 'Chỉ khoảng đo sạch', 'Cao (≥ 4/5 khoảng đo) / Trung bình'],
  ['B', '25% < lỗi ≤ 50%', String(tiers.B), 'Chỉ khoảng đo sạch', 'Thấp'],
  ['C', 'Lỗi > 50%', String(tiers.C), 'Toàn bộ khoảng đo (trừ sentinel)', 'Rất thấp — gợi ý xác minh'],
  ['X', 'Dưới 50% khung dùng được, hoặc không có số đo trong 7 ngày cuối lịch sử', String(tiers.X), 'Không chấm điểm', 'Gợi ý bảo trì'],
], [0.8, 3.2, 1.3, 2.4, 2.3]))

C.push(H2('2.7. Giả định và giới hạn'))
C.push(...box('Giả định và giới hạn', [
  'Không có speed: occupancy là chỉ báo tắc nghẽn; "sự kiện" là định nghĩa thống kê (z ≥ 2 và +5 điểm %), chưa đối chiếu với nhật ký sự cố thực.',
  'Dữ liệu chỉ T1–T6/2015; mô hình chưa thấy mùa hè, mùa thu. Chạy với dữ liệu mùa khác cần chạy lại build (K-means, baseline, mô hình).',
  `Khung đêm (00–05 giờ) phần lớn "Không đủ dữ liệu" (35–45%) do khoảng đo error tập trung khi lưu lượng gần 0; tỷ lệ Không đủ dữ liệu cả tháng 6: ${vn(lv.dist['Không đủ dữ liệu'], 1)}%.`,
  'Ngưỡng 30 phút và định nghĩa sự kiện quyết định nhãn; thay đổi chúng cần huấn luyện lại.',
  '**Recall sự kiện "đang diễn ra" cao một phần do cách định nghĩa:** nhãn sự kiện và C1 cùng dựa trên z occupancy so với baseline, nên mức Cao bắt gần hết sự kiện đang diễn ra là gần như tất yếu. Không có nhật ký sự cố thực để làm nhãn độc lập, nên chất lượng thật của DSS được đánh giá chủ yếu qua recall sự kiện **sắp xảy ra**, precision@10 và PR-AUC của C5 so với mốc Persistence.',
  WX ? `**Thời tiết (nguồn ngoài):** thêm thời tiết theo ngày (lượng mưa, tuyết, nhiệt độ, số giờ mưa) làm đặc trưng cho C5 thay đổi PR-AUC tháng 5 từ ${vn(WX.pr_auc_base, 4)} thành ${vn(WX.pr_auc_weather, 4)} (Δ ${WX.pr_auc_weather >= WX.pr_auc_base ? '+' : ''}${vn(WX.pr_auc_weather - WX.pr_auc_base, 4)}) — ${Math.abs(WX.pr_auc_weather - WX.pr_auc_base) < 0.005 ? 'không đáng kể' : 'có thay đổi'}, nên DSS chưa dùng thời tiết làm đầu vào. Tỷ lệ sự kiện ban ngày (6–20 giờ) ở ngày mưa ≥ 1 mm là ${pc(WX.event_rate_rain, 2)} so với ${pc(WX.event_rate_dry, 2)} ở ngày khô. Nguyên nhân: dữ liệu theo ngày quá thô so với khung 15 phút, và hệ số mức chung toàn thành phố (city factor) đã khử phần lớn tác động đồng loạt của mưa. Dữ liệu thời tiết vẫn nằm trong DW để phân tích OLAP; hướng phát triển là thời tiết theo giờ.` : 'Thời tiết chỉ có theo ngày, quá thô so với khung 15 phút; chưa dùng làm đầu vào của DSS.',
  'Trần độ chính xác của C5 chủ yếu do bản chất bài toán: ùn tắc bất thường không lặp lại theo giờ, nhãn 15 phút nhiễu. Đã thử thêm 12 đặc trưng (z cùng khung hôm trước/tuần trước, max/trung bình trượt 1–2 giờ, z lớn nhất ở lân cận, tỷ lệ sự kiện lịch sử theo detector × giờ) và nhãn trung bình 30 phút — PR-AUC không tăng (0,378–0,379 so với 0,380), nên không đưa vào. Cải thiện tiếp cần dữ liệu ngoài: sự cố, công trường, tín hiệu đèn, thời tiết.',
  'C4 dùng khoảng cách đường chim bay, không theo mạng đường; tương quan không gian yếu nên trọng số nhỏ.',
  'Cột error chưa có codebook; tier C chỉ mang tính tham khảo.',
  'Dữ liệu UTD19 theo giấy phép CC BY-NC-SA 4.0 (phi thương mại, trích dẫn Loder et al., 2019, Scientific Reports 9, 16283).',
]))

// ===== 3 =====
C.push(H1('3. Kiến trúc hiện thực'))
C.push(...table(['Tầng', 'Thành phần', 'Vai trò'], [
  ['Data Warehouse', 'sql/30_dw/38_fact_traffic_15min.sql, sql/40_mart/43_dss_detector_window.sql', 'Fact gốc 3 phút → fact tổng hợp dw.fact_traffic_15min → mart.dss_detector_window. Khi chỉ có bản xuất 15 phút, pipeline nạp thẳng fact tổng hợp (--from-export); DSS không phân biệt hai chế độ'],
  ['Engine (offline)', 'utd19_dss/build.py', `Nạp dữ liệu, luật DQ, K-means, baseline, huấn luyện & chọn mô hình, tối ưu trọng số, kiểm thử tháng 6; ghi artifacts (khoảng ${Math.round(meta.seconds / 60)} phút)`],
  ['Engine (live)', 'utd19_dss/live.py, engine.py, scoring.py', 'Nhận từng khung (phát lại hoặc POST /api/ingest), tính C1–C5, điểm, mức, hành động (≈ 15 ms/khung); kết quả trùng khớp 100% với chạy lô'],
  ['Lưu trữ kết quả', 'data/work/dss_results.duckdb', 'dss.priority_live (kết quả từng khung), dss.action_log (nhật ký quyết định)'],
  ['Backend', 'utd19_dss/api.py (FastAPI)', 'REST: /api/state, /api/replay, /api/window(.csv), /api/timeline, /api/detector/{id}, /api/whatif, /api/goalseek, /api/actions, /api/model, /api/dw/quality, /api/ingest'],
  ['Frontend', 'frontend/ (React + Vite, Leaflet, Recharts)', '8 màn hình mục 1.4; bản build nằm trong frontend/dist và được FastAPI phục vụ tại cổng 8000'],
], [2, 3.6, 4.4]))
C.push(H3('3.1. Bốn phân hệ DSS và phân loại (Chương 6)'))
C.push(...table(['Phân hệ', 'Hiện thực', 'Vai trò'], [
  ['Quản lý dữ liệu', 'Kho dữ liệu DuckDB (staging → clean → lược đồ sao → mart), etl.run_log / quarantine / reconciliation / metadata_catalog; dss_results.duckdb', 'Lưu, làm sạch, tích hợp dữ liệu đo, lịch và thời tiết; lưu kết quả chấm điểm và nhật ký quyết định'],
  ['Quản lý mô hình', 'Model base: baseline thống kê, K-means (ngày, detector), DT / NB / MLP / GB, tổng hợp đa tiêu chí, tối ưu lưới, hiệu chỉnh isotonic. MBMS: build.py + meta.json (dựng, chọn, lưu phiên bản)', 'Chạy, so sánh, chọn mô hình; what-if, độ nhạy, goal seeking'],
  ['Tri thức', 'Bảng quyết định 13 luật; luật rút từ cây quyết định giải thích từng cảnh báo; luật chất lượng dữ liệu (tier A/B/C/X)', 'Chuyển điểm số thành hành động cụ thể và lý do'],
  ['Giao diện (dialog)', 'Dashboard web React (mục 1.4) qua REST API', 'Xếp hạng live, bản đồ, chi tiết, what-if, goal seeking, ghi nhận quyết định, xem chất lượng DW'],
], [2, 4.6, 3.4]))
C.push(P('**Phân loại.** Theo Holsapple & Whinston: **DSS phức hợp** (compound) — hướng cơ sở dữ liệu (kho dữ liệu) + hướng bộ giải (mô hình học máy, tối ưu trọng số) + hướng luật (bảng quyết định). Theo Power: **DSS lai** (data-driven + model-driven + knowledge-driven). Theo Alter: hệ **gợi ý** (suggestion model) — đầu ra đề xuất hành động cụ thể nhưng người vận hành quyết định. Triển khai dạng **web-based DSS**; phát triển theo **prototyping** (v1 → v5.1), đúng xu hướng phát triển DSS ở Chương 8.'))
C.push(H3('Cách chạy'))
;['pip install -e .[dev,dss]   (cài thêm scikit-learn, fastapi, uvicorn, joblib)',
  'python -m utd19_dw.weather   (tùy chọn) rồi python -m utd19_dw.pipeline   (dựng DW → data/work/utd19.duckdb)',
  'python -m utd19_dss.build   (dựng artifacts từ mart của DW; chỉ khi chưa có DW mới đọc tệp CSV khung 15 phút)',
  'python -m utd19_dss.evaluate   (đánh giá trên tháng 6, ghi báo cáo vào reports/)',
  'uvicorn utd19_dss.api:app --port 8000   rồi mở http://localhost:8000',
].forEach((t) => C.push(N(t)))

// ===== Phụ lục A =====
C.push(brk())
if (EV) {
  const S0 = EV.strategies
  C.push(H1('4. Đánh giá hệ thống hỗ trợ ra quyết định'))
  C.push(P(`Đánh giá do module utd19_dss/evaluate.py thực hiện (python -m utd19_dss.evaluate); kết quả đầy đủ ở reports/dss_evaluation.md (kèm bảng CSV và biểu đồ). Mọi lựa chọn làm trên tháng 5, mọi con số dưới đây đo trên **tháng 6** — dữ liệu hệ thống chưa thấy khi dựng. Tháng 6 có ${vn(EV.events_june.total)} detector-khung cần chú ý: ${vn(EV.events_june.now)} đang diễn ra và ${vn(EV.events_june.future_only)} chỉ xảy ra trong 30 phút tới.`))
  C.push(H2('4.1. So sánh chiến lược ra quyết định'))
  C.push(...table(['Chiến lược', 'Ngưỡng', 'P@10', 'Cao/ khung', 'Precision Cao', 'Recall Cao', 'F1 Cao', 'Recall đang diễn ra', 'Recall sắp xảy ra'],
    S0.map((r, i) => ({ cells: [r.strategy, `${r.thresholds.high}/${r.thresholds.medium}`, pc(r.p_at_10), vn(r.high_per_window, 1), pc(r.precision_high), pc(r.recall_high), vn(r.f1_high, 3), pc(r.recall_now_high), pc(r.recall_future_high)], fill: i === 0 ? 'E2EFDA' : undefined })),
    [2.8, 0.9, 0.9, 0.8, 1, 1, 1.05, 1.1, 1.1], { num: [2, 3, 4, 5, 6, 7, 8] }))
  {
    const v5 = S0[0], v4 = strat('v4 — '), v4r = strat('v4 + '), noc5 = strat('v5 bỏ C5'), c5 = strat('Chỉ C5'), c1 = strat('Chỉ C1')
    C.push(P(`So với v4, v5 tăng F1 mức Cao từ ${vn(v4.f1_high, 3)} lên ${vn(v5.f1_high, 3)} và P@10 từ ${pc(v4.p_at_10)} lên ${pc(v5.p_at_10)}. Tách tác động: chỉ chọn lại ngưỡng cho v4 đã nâng F1 lên ${vn(v4r.f1_high, 3)}; thêm học máy (so "v5 bỏ C5" ${vn(noc5.f1_high, 3)} với v5) đóng góp phần còn lại, chủ yếu qua recall sự kiện sắp xảy ra (${pc(noc5.recall_future_high)} → ${pc(v5.recall_future_high)}). Kết hợp luật và học máy tốt hơn dùng riêng C5 (${vn(c5.f1_high, 3)}) hoặc riêng C1 (${vn(c1.f1_high, 3)}). Các chiến lược chọn lại ngưỡng đều áp cùng giới hạn năng lực ca trực với v5; v4 gốc giữ nguyên cấu hình cũ.`))
  }
  C.push(H2('4.2. Loại bỏ từng tiêu chí'))
  C.push(...table(['Bỏ tiêu chí', 'P@10', 'F1 Cao', 'Δ P@10 (điểm %)', 'Δ F1 Cao'], EV.ablation.map((r) => [`${r.criterion_removed} — ${r.label}`, pc(r.p_at_10), vn(r.f1_high, 3), vn(r.delta_p_at_10 * 100, 1), vn(r.delta_f1_high, 3)]), [4.4, 1.3, 1.3, 1.6, 1.4], { num: [1, 2, 3, 4] }))
  C.push(P('C5 và C1 là hai tiêu chí quyết định chất lượng xếp hạng. C2, C3, C4 thay đổi kết quả rất ít (|Δ F1| ≤ 0,015) vì thông tin của chúng đã nằm trong đặc trưng của C5; chúng được giữ với trọng số nhỏ vì bảng quyết định dùng chúng để chọn loại hành động và để người vận hành hiểu lý do.'))
  C.push(H2('4.3. Ổn định, chất lượng dữ liệu và hiệu năng'))
  const pd = EV.per_day_summary
  C.push(B(`Theo ngày: F1 mức Cao trung bình ${vn(pd.f1_high_v5_mean, 3)} ± ${vn(pd.f1_high_v5_std, 3)}; v5 tốt hơn v4 ở ${pd.days_v5_better}/${pd.days} ngày.`))
  C.push(B(`Theo tier (nhóm X không được chấm): ${EV.per_tier.filter((r) => r.tier !== 'X').map((r) => `tier ${r.tier} precision ${pc(r.precision_high)}, recall ${pc(r.recall_high)}`).join('; ')}.`))
  C.push(B(`Xác suất C5 được hiệu chỉnh tốt: ở mọi khoảng, xác suất dự báo lệch tỷ lệ thực tế không quá vài điểm %, nên có thể hiển thị trực tiếp.`))
  C.push(B(`Hiệu năng live: ${vn(EV.performance.ms_per_window_median, 1)} ms để chấm một khung 15 phút cho ${EV.performance.detectors} detector.`))
  C.push(H2('4.4. Kết luận'))
  C.push(P(`DSS v5 phát hiện gần như đầy đủ bất thường đang diễn ra (mức Cao ${pc(S0[0].recall_now_high)}, tính cả Trung bình ${pc(S0[0].recall_now_high_med)}) với độ chính xác cao hơn v4, và cảnh báo trước được một phần sự kiện sắp xảy ra (${pc(S0[0].recall_future_high_med)} ở mức Cao + Trung bình). Giới hạn chính là dự báo 15–30 phút trước với dữ liệu chỉ từ vòng từ; cần thêm dữ liệu sự cố, công trường, tín hiệu đèn hoặc thời tiết để cải thiện tiếp.`))
  C.push(brk())
}
C.push(H1('Phụ lục A — Tóm tắt profiling dữ liệu Luzern'))
C.push(H2('A.1. Tổng quan'))
C.push(...table(['Chỉ tiêu', 'Giá trị'], [
  ['Số dòng khung 15 phút', `${vn(pr.rows)} (detector × ngày × khung)`],
  ['Số detector có số đo', `${pr.detectors}; ${pr.full_days_detectors} có số đo đến cuối giai đoạn lịch sử`],
  ['Số ngày', `${pr.days}: ${dmy(pr.first_day)} – ${dmy(pr.last_day)}`],
  ['Số ngày theo thứ', Object.entries(pr.dow_counts).map(([k, v]) => `${k}: ${v}`).join(', ')],
  ['Loại đường (fclass)', Object.entries(pr.fclass).map(([k, v]) => `${k} ${v}`).join(', ')],
  ['Lưu lượng trung bình mỗi detector', `Trung vị ${vn(pr.mean_flow_quantiles['0.5'])} xe/giờ/làn (P25 ${vn(pr.mean_flow_quantiles['0.25'])}, P75 ${vn(pr.mean_flow_quantiles['0.75'])}, lớn nhất ${vn(pr.mean_flow_quantiles['1.0'])})`],
  ['Occupancy trung bình mỗi detector', `Trung vị ${vn(pr.mean_occ_quantiles['0.5'], 3)} (lớn nhất ${vn(pr.mean_occ_quantiles['1.0'], 3)})`],
  ['Khung bị loại', `slot 96: ${vn(pr.dropped.slot_out_of_range)}; cảm biến kẹt: ${vn(pr.dropped.stuck_windows)} khung; không hợp lệ tổng: ${vn(pr.dropped.invalid_windows)} khung`],
], [3, 7]))
C.push(H2('A.2. Chất lượng dữ liệu theo detector (cột error)'))
C.push(...table(['Tỷ lệ khoảng đo bị gắn error', 'Số detector'], Object.entries(pr.error_bins).map(([k, v]) => [k, String(v)]), [6, 4], { num: [1] }))
C.push(...table(['Giờ', '00', '01', '02', '03', '04', '05', '06', '07', '08–19', '20', '21', '22', '23'],
  [['Tỷ lệ error (tier A)', '32%', '40%', '42%', '45%', '46%', '33%', '15%', '10%', '3–6%', '5%', '8%', '11%', '20%']],
  [2.6, 0.6, 0.6, 0.6, 0.6, 0.6, 0.6, 0.6, 0.6, 0.9, 0.6, 0.6, 0.6, 0.6]))
C.push(P('Khác Toronto (error gần đều theo giờ), ở Luzern error là đặc tính của khung đêm khi lưu lượng ≈ 0 (48% khoảng đo ở khung toàn số 0 bị gắn error, so với 11% ở khung có xe).'))
C.push(H2('A.3. Vị trí và tương quan không gian'))
C.push(P(`Phần dư occupancy (đã trừ baseline và mức chung toàn thành phố) của detector tier A, tính trên giai đoạn lịch sử. Mỗi detector có trung vị ${vn(meta.neighbors_per_detector.median)} lân cận hợp lệ trong 50 m – 0,5 km.`))
C.push(...table(['Khoảng cách', 'Số cặp', 'Tương quan trung bình', 'Trung vị'], sc.map((r) => [r.bin, vn(r.pairs), vn(r.mean, 3), vn(r.median, 3)]), [3, 2, 3, 2], { num: [1, 2, 3] }))
C.push(P('Tương quan về ~0 từ 0,5 km nên bán kính C4 thu từ 1 km (v4) xuống 0,5 km, σ = 0,3 km. Ngay cả các làn cùng điểm đo (< 50 m) chỉ tương quan 0,21 — yếu hơn Toronto (0,61) — vì các làn ở nút giao Luzern thường phục vụ hướng rẽ khác nhau.'))

// ===== Phụ lục B =====
C.push(H1('Phụ lục B — Kết quả chạy engine'))
C.push(P(`Chạy python -m utd19_dss.build trên ${vn(pr.rows)} dòng khung 15 phút, ${pr.detectors} detector; thời gian ${vn(meta.seconds)} giây trên máy 2 nhân (phần lớn cho MLP và tìm kiếm lưới trọng số).`))
C.push(H2('B.1. Kiểm thử ngoài mẫu tháng 6 (mô hình C5)'))
C.push(...table(['Mô hình', 'PR-AUC', 'ROC-AUC', 'Precision', 'Recall', 'F1', 'Recall sự kiện mới'],
  Object.entries(mt).map(([k, r]) => ({ cells: [LBL[k], vn(r.pr_auc, 3), vn(r.roc_auc, 3), pc(r.precision), pc(r.recall), vn(r.f1, 3), pc(r.onset_recall)], fill: k === best ? 'E2EFDA' : undefined })),
  [3.4, 1.1, 1.1, 1.1, 1.1, 1, 1.4], { num: [1, 2, 3, 4, 5, 6] }))
C.push(P(`Quét độ sâu Decision Tree (PR-AUC tháng 5): ${meta.dt_scan.map((r) => `${r.max_depth}: ${vn(r.pr_auc, 3)}`).join('; ')} — bão hòa từ độ sâu 8–10. Đặc trưng quan trọng nhất (cây giải thích): ${fi.slice(0, 5).map((f) => `${f.feature} (${vn(f.importance, 3)})`).join(', ')}.`))
C.push(H2('B.2. Priority Score: v5 so với v4 trên tháng 6'))
C.push(...table(['Chỉ số (tháng 6, cùng tiêu chí)', 'v5', 'v4 (0,45/0,20/0,25/0,10; 70/40)'], [
  ['Precision@10 (cần chú ý ngay hoặc trong 30 phút)', pc(meta.p_at_10.test_v5), pc(meta.p_at_10.test_v4)],
  ['Tỷ lệ khung mức Cao', pc(lv.dist['Cao'] / 100, 2), pc(lv4.dist['Cao'] / 100, 2)],
  ['Precision mức Cao', pc(lv.precision['Cao']), pc(lv4.precision['Cao'])],
  ['Precision mức Trung bình', pc(lv.precision['Trung bình']), pc(lv4.precision['Trung bình'])],
  ['Tỷ lệ cần chú ý trong mức Thấp (bỏ sót)', pc(lv.precision['Thấp']), pc(lv4.precision['Thấp'])],
  ['Recall sự kiện ở mức Cao', pc(lv.event_recall_high), pc(lv4.event_recall_high)],
  ['Detector Cao trung bình / khung', vn(lv.high_per_window_mean, 2), vn(lv4.high_per_window_mean, 2)],
  ['Khung có ≥ 1 detector Cao', `${vn(lv.windows_with_high_pct, 1)}%`, `${vn(lv4.windows_with_high_pct, 1)}%`],
], [5, 2.2, 2.8]))
C.push(P(`Recall sự kiện (tỷ lệ detector-khung cần chú ý được xếp mức Cao) trên toàn tháng 6: **v5 ${pc(lv.event_recall_high)}** so với v4 ${pc(lv4.event_recall_high)}; tính cả mức Trung bình: ${pc(lv.event_recall_high_med)} so với ${pc(lv4.event_recall_high_med)}. Precision mức Cao: ${pc(lv.precision['Cao'])} so với ${pc(lv4.precision['Cao'])}. v4 có ít cảnh báo Cao hơn (${vn(lv4.high_per_window_mean, 2)} so với ${vn(lv.high_per_window_mean, 2)} mỗi khung) nhưng bỏ sót phần lớn sự kiện vì ngưỡng 70 đặt theo kinh nghiệm.`))
C.push(H2('B.3. Phân tích độ nhạy trọng số (tháng 5)'))
C.push(...table(['Thay đổi', 'Bù vào', 'Precision@10', 'Chênh (điểm %)'],
  meta.sensitivity.map((s) => [`${s.criterion} ${s.delta > 0 ? '+' : ''}${vn(s.delta, 2)}`, s.compensate, pc(s.p_at_10, 2), vn((s.p_at_10 - meta.p_at_10.valid_v5) * 100, 2)]),
  [3, 2, 2.5, 2.5], { num: [2, 3] }))

// ===== Phụ lục C =====
C.push(H1('Phụ lục C — Kết quả K-means'))
C.push(H2('C.1. Phân cụm ngày (151 ngày lịch sử)'))
const DOWN = ['Thứ 2', 'Thứ 3', 'Thứ 4', 'Thứ 5', 'Thứ 6', 'Thứ 7', 'Chủ nhật']
C.push(...table(['Thứ', 'Cụm Ngày làm việc', 'Cụm Thứ Bảy', 'Cụm Chủ nhật / Lễ'], DOWN.map((d, i) => [d, String(ct.WD?.[i] ?? 0), String(ct.SAT?.[i] ?? 0), String(ct.SUN?.[i] ?? 0)]), [3, 2.4, 2.2, 2.4], { num: [1, 2, 3] }))
C.push(...table(['Ngày', 'Theo lịch', 'Theo K-means', 'Mức lưu lượng TB', 'Ghi chú'], kd.mismatch.map((r) => [dmy(r.day), TYPE[r.calendar], TYPE[r.cluster], vn(r.level, 1), DAYNOTE[r.day] || '']), [1.6, 2, 2, 1.6, 3.8]))
C.push(H2('C.2. Phân cụm detector'))
C.push(...table(['k', 'Silhouette', 'Kích thước cụm'], kdet.scan.map((s) => [String(s.k), vn(s.silhouette, 3), s.sizes.join(' / ')]), [1.5, 2.5, 6]))
C.push(...table([`Cụm (k = ${kdet.k})`, 'Số detector', 'Đặc điểm'], Object.entries(kdet.sizes).map(([k, v]) => [k, String(v), {
  'Đỉnh buổi chiều': 'Occupancy đạt đỉnh 16–18 giờ, sáng thấp — hướng ra khỏi trung tâm',
  'Đỉnh buổi sáng': 'Đỉnh 7–9 giờ — hướng vào trung tâm',
  'Hai đỉnh sáng–chiều': 'Tải cao suốt ban ngày với hai đỉnh tương đương',
  'Tải rất thấp': 'Gần như không có xe — kiểm tra lắp đặt/cấu hình',
}[k] || '']), [3, 1.6, 5.4]))

const doc = new Document({
  creator: 'Vinh', title: 'Thiết kế DSS v5.1 — Luzern',
  styles: {
    default: { document: { run: { font: 'Calibri', size: 22 } } },
    paragraphStyles: [
      { id: 'Heading1', name: 'Heading 1', basedOn: 'Normal', next: 'Normal', quickFormat: true, run: { size: 32, bold: true, color: BLUE, font: 'Calibri' }, paragraph: { spacing: { before: 360, after: 160 }, outlineLevel: 0 } },
      { id: 'Heading2', name: 'Heading 2', basedOn: 'Normal', next: 'Normal', quickFormat: true, run: { size: 26, bold: true, color: BLUE, font: 'Calibri' }, paragraph: { spacing: { before: 240, after: 120 }, outlineLevel: 1 } },
    ],
  },
  numbering: { config: [
    { reference: 'bul', levels: [{ level: 0, format: LevelFormat.BULLET, text: '•', alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 360, hanging: 240 } } } },
      { level: 1, format: LevelFormat.BULLET, text: '◦', alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 240 } } } }] },
    { reference: 'num', levels: [{ level: 0, format: LevelFormat.DECIMAL, text: '%1.', alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 360, hanging: 300 } } } }] },
  ] },
  features: { updateFields: true },
  sections: [{
    properties: { page: { size: { width: 12240, height: 15840 }, margin: { top: 1440, bottom: 1440, left: 1350, right: 1350 } } },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ children: [PageNumber.CURRENT], color: '808080', size: 18 })] })] }) },
    children: C,
  }],
})
Packer.toBuffer(doc).then((b) => { fs.writeFileSync(OUT, b); console.log('Đã ghi', OUT) })
