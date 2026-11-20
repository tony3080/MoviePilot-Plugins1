import SwiftUI

struct StatusBadge: View {
    let state: String
    private var color: Color {
        if ["failed", "error", "unidentified", "rolled_back"].contains(state) { return .red }
        if ["completed", "succeeded", "imported", "exists", "existing"].contains(state) { return .green }
        if ["pending", "pending_import"].contains(state) { return .purple }
        if ["running", "importing", "queued", "download_only"].contains(state) { return .orange }
        return .blue
    }
    var body: some View {
        Text(statusText(state)).font(.caption.weight(.medium)).foregroundStyle(color)
            .lineLimit(1)
            .padding(.horizontal, 7).padding(.vertical, 4).background(color.opacity(0.1), in: RoundedRectangle(cornerRadius: 5))
    }
}

struct InfoBadge: View {
    let text: String
    var color: Color = .secondary
    var body: some View {
        Text(text)
            .font(.caption2.weight(.medium))
            .foregroundStyle(color)
            .padding(.horizontal, 7)
            .padding(.vertical, 4)
            .background(color.opacity(0.12), in: RoundedRectangle(cornerRadius: 5))
            .overlay { RoundedRectangle(cornerRadius: 5).stroke(color.opacity(0.18), lineWidth: 0.6) }
            .lineLimit(1)
    }
}

struct BadgeFlowLayout: Layout {
    var spacing: CGFloat = 5
    var rowSpacing: CGFloat = 4

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        arrangement(width: proposal.width, subviews: subviews).size
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let frames = arrangement(width: bounds.width, subviews: subviews).frames
        for (subview, frame) in zip(subviews, frames) {
            subview.place(at: CGPoint(x: bounds.minX + frame.minX, y: bounds.minY + frame.minY),
                          anchor: .topLeading, proposal: ProposedViewSize(frame.size))
        }
    }

    private func arrangement(width proposedWidth: CGFloat?, subviews: Subviews) -> (size: CGSize, frames: [CGRect]) {
        guard !subviews.isEmpty else { return (.zero, []) }
        let idealSizes = subviews.map { $0.sizeThatFits(.unspecified) }
        let naturalWidth = idealSizes.reduce(0) { $0 + $1.width } + CGFloat(subviews.count - 1) * spacing
        let width = proposedWidth.flatMap { $0.isFinite ? max(0, $0) : nil } ?? naturalWidth
        var frames: [CGRect] = []
        var x: CGFloat = 0
        var y: CGFloat = 0
        var rowHeight: CGFloat = 0

        for (subview, idealSize) in zip(subviews, idealSizes) {
            let size = subview.sizeThatFits(ProposedViewSize(width: min(idealSize.width, width), height: nil))
            if x > 0 && x + size.width > width {
                x = 0
                y += rowHeight + rowSpacing
                rowHeight = 0
            }
            frames.append(CGRect(origin: CGPoint(x: x, y: y), size: size))
            x += size.width + spacing
            rowHeight = max(rowHeight, size.height)
        }
        return (CGSize(width: width, height: y + rowHeight), frames)
    }
}

struct Poster: View {
    let path: String
    var width: CGFloat = 100
    var height: CGFloat = 150
    var body: some View {
        AsyncImage(url: safeWebURL(path)) { image in image.resizable().scaledToFill() } placeholder: {
            Rectangle().fill(Color.secondary.opacity(0.12)).overlay { Image(systemName: "film").foregroundStyle(.secondary) }
        }
        .frame(width: width, height: height).clipped()
        .accessibilityHidden(true)
    }
}

struct RecordRow: View {
    let item: Record
    let qb: Bool
    var selected = false
    var onSelect: (() -> Void)? = nil
    var onAction: ((String) -> Void)? = nil
    var analysisTask: JSONValue = .null
    @State private var showFilename = false
    @ScaledMetric(relativeTo: .body) private var scaledPosterWidth = 140
    private var posterWidth: CGFloat { min(156, scaledPosterWidth) }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            summary.allowsHitTesting(false)
            HStack(spacing: 8) {
                Text(item.sourceFileName)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .truncationMode(.tail)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .accessibilityIdentifier("source-\(item.id)")
                    .allowsHitTesting(false)
                if !item.sourceFileName.isEmpty {
                    Button { showFilename = true } label: {
                        Image(systemName: "info.circle").frame(width: 44, height: 44)
                            .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .foregroundStyle(Color.accentColor)
                    .accessibilityLabel("完整文件名：\(item.title)")
                    .accessibilityIdentifier("detail-\(item.id)")
                    .popover(isPresented: $showFilename, attachmentAnchor: .rect(.bounds), arrowEdge: .bottom) {
                        Text(item.sourceFileName)
                            .font(.footnote)
                            .textSelection(.enabled)
                            .padding(12)
                            .frame(width: 300, alignment: .leading)
                            .fixedSize(horizontal: false, vertical: true)
                            .accessibilityIdentifier("filename-popover-\(item.id)")
                            .presentationCompactAdaptation(.popover)
                    }
                }
            }
        }
        .padding(.vertical, 10)
        .padding(.trailing, 12)
        .padding(.leading, posterWidth + 12)
        .frame(maxWidth: .infinity, minHeight: posterWidth * 1.5, alignment: .topLeading)
        .background(alignment: .leading) {
            GeometryReader { geometry in
                Poster(path: item.poster, width: posterWidth, height: geometry.size.height)
                    .allowsHitTesting(false)
                    .overlay { posterControls }
            }
            .frame(width: posterWidth)
        }
        .background {
            if let onSelect {
                Button(action: onSelect) {
                    Rectangle().fill(Color(uiColor: .secondarySystemGroupedBackground))
                }
                .buttonStyle(.plain)
                .accessibilityLabel("选择：\(item.title)")
                .accessibilityValue(selected ? "已选中" : "未选中")
                .accessibilityIdentifier("select-\(item.id)")
            } else {
                Color(uiColor: .secondarySystemGroupedBackground)
            }
        }
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .overlay {
            RoundedRectangle(cornerRadius: 8)
                .stroke(selected ? Color.accentColor : item.inventoryIncomplete ? .red : .clear, lineWidth: 2)
                .allowsHitTesting(false)
        }
        .accessibilityElement(children: .contain)
    }

    private var analysisRunning: Bool { ["queued", "running"].contains(analysisTask["state"].text) }
    private var posterControls: some View {
        VStack(spacing: 6) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 4) {
                    HStack(spacing: 0) {
                        posterLink("P", color: Color(red: 242/255, green: 154/255, blue: 46/255), url: item.sourceURL)
                        posterLink("T", color: Color(red: 32/255, green: 183/255, blue: 207/255), url: item.tmdbURL)
                    }
                    if item.rolledBack {
                        PosterBadge(letter: "R", color: Color(red: 132/255, green: 86/255, blue: 232/255),
                                    message: "已回退" + (item.failure.isEmpty ? "" : "：\(item.failure)"))
                    } else if !item.failure.isEmpty {
                        PosterBadge(letter: "!", color: .red, message: item.failure)
                    }
                }
                Spacer(minLength: 0)
                VStack(spacing: 4) {
                    if !qb && item.state == "pending" { posterAction("xmark", title: "删除插件记录", action: "delete") }
                    posterAction("arrow.clockwise", title: "刷新", action: "refresh")
                    if item.canEdit(qb: qb) { posterAction("pencil", title: "人工识别", action: "edit") }
                    if item.canMarkUnidentified(qb: qb) {
                        posterAction("questionmark.circle", title: "移入未识别", action: "unidentify")
                    }
                }
            }
            Spacer(minLength: 12)
            if item.details["version_count"].int > 1 {
                Text("\(item.details["version_count"].int)in1")
                    .font(.caption2.weight(.semibold)).foregroundStyle(.white)
                    .padding(3).background(.black.opacity(0.7), in: RoundedRectangle(cornerRadius: 4))
                    .frame(maxWidth: .infinity, alignment: .trailing)
                    .allowsHitTesting(false)
            }
            HStack(spacing: 0) {
                statusBadge("S", kind: "sha1")
                statusBadge("M", kind: "metadata")
                statusBadge("I", kind: "intro")
                Spacer(minLength: 0)
                statusBadge("Y", kind: "year")
            }
        }
        .padding(6)
    }

    private func posterLink(_ letter: String, color: Color, url: URL?) -> some View {
        Group {
            if let url {
                Link(destination: url) { PosterBadgeFace(letter: letter, color: color) }
            } else {
                PosterBadge(letter: letter, color: .posterNeutral,
                            message: letter == "P" ? "未获取到来源链接" : "未获取到 TMDB 链接")
            }
        }
        .buttonStyle(.plain)
        .accessibilityLabel(letter == "P" ? "来源页面" : "TMDB 页面")
        .accessibilityIdentifier("poster-\(letter)-\(item.id)")
    }

    private func posterAction(_ symbol: String, title: String, action: String) -> some View {
        Button { onAction?(action) } label: {
            Image(systemName: symbol).font(.system(size: 15, weight: .semibold))
                .foregroundStyle(.white).frame(width: 28, height: 28)
                .background(.black.opacity(0.78), in: RoundedRectangle(cornerRadius: 5))
                .frame(width: 32, height: 32).contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .disabled(onAction == nil || (action == "refresh" && item.state == "importing"))
        .help(title).accessibilityLabel(title)
        .accessibilityIdentifier("poster-\(action)-\(item.id)")
    }

    private func statusBadge(_ letter: String, kind: String) -> some View {
        let status = item.posterStatus(kind)
        let canRun = ["metadata", "intro"].contains(kind) && onAction != nil
            && item.canAnalyze(kind, qb: qb) && !analysisRunning
        let running = analysisRunning && analysisTask["result"]["media_id"].text == item.analysisID(qb: qb)
            && analysisTask["result"]["kind"].text == kind
        return PosterBadge(letter: letter, color: status.color,
                           message: running ? "正在逐文件提取" : status.message,
                           running: running,
                           retry: canRun ? { onAction?("analyze-\(kind)") } : nil)
            .accessibilityIdentifier("poster-\(letter)-\(item.id)")
    }

    @ViewBuilder private var summary: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(item.title).font(.headline).lineLimit(2)
            BadgeFlowLayout { rowLabels }
            if !item.directoryName.isEmpty {
                Text(item.directoryName)
                    .font(.system(.caption, design: .monospaced))
                    .foregroundStyle(Color(red: 22.0 / 255, green: 177.0 / 255, blue: 1))
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier("directory-\(item.id)")
            }
            if !item.inventorySummary.isEmpty {
                Text(item.inventorySummary)
                    .font(.caption2.weight(.medium))
                    .foregroundStyle(inventoryColor)
                    .padding(.top, 1)
            }
            if !item.failure.isEmpty {
                Label(item.failure, systemImage: "exclamationmark.circle")
                    .font(.caption).foregroundStyle(.red).lineLimit(2)
            }
            if item.labels["status"].text == "failed" {
                Label("站点标签获取失败", systemImage: "tag.slash")
                    .font(.caption).foregroundStyle(.orange)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    @ViewBuilder private var rowLabels: some View {
        StatusBadge(state: qb ? (item["inventory_state"].text == "exists" ? "existing" :
            item["recognition_state"].text == "unidentified" ? "unidentified" :
            item.details["import_control"]["import_enabled"] == .bool(false) ? "download_only" : "pending_import") :
            item.state == "rolled_back" ? "identified" : item.state)
        if qb { InfoBadge(text: "\(Int(min(1, max(0, item["progress"].double)) * 100))%", color: .blue) }
        if !item.seasonLabel.isEmpty { InfoBadge(text: item.seasonLabel, color: .purple) }
        if !item.resolution.isEmpty { InfoBadge(text: item.resolution, color: .cyan) }
        if !item.mediaCategory.isEmpty { InfoBadge(text: item.mediaCategory, color: .purple) }
        if !item.customization.isEmpty { InfoBadge(text: item.customization, color: .teal) }
        let bytes = item["size"].double > 0 ? item["size"].double : item.details["torrent"]["size"].double
        if bytes > 0 { InfoBadge(text: sizeText(bytes), color: .secondary) }
        if item.labels["mandarin"].flag { InfoBadge(text: "国配", color: .red) }
        if item.labels["effects"].flag { InfoBadge(text: "特效", color: .teal) }
        if item.inventoryIncomplete { InfoBadge(text: "库存不完整", color: .red) }
    }

    private var inventoryColor: Color {
        switch item.inventoryTone {
        case "ok": return .green
        case "warning": return .orange
        case "complete": return .green
        default: return .red
        }
    }
}

extension Color {
    static let posterNeutral = Color(red: 107/255, green: 114/255, blue: 128/255)
}

extension PosterStatus {
    var color: Color {
        switch tone {
        case .success: return Color(red: 21/255, green: 128/255, blue: 61/255)
        case .failure: return Color(red: 220/255, green: 38/255, blue: 38/255)
        case .neutral: return .posterNeutral
        }
    }
}

struct PosterBadgeFace: View {
    let letter: String
    let color: Color
    var running = false
    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 5).fill(color)
            if running { ProgressView().tint(.white).scaleEffect(0.65) }
            else { Text(letter).font(.system(size: 15, weight: .heavy)).foregroundStyle(.white) }
        }
        .frame(width: 28, height: 28)
        .shadow(color: .black.opacity(0.25), radius: 3, y: 1)
        .frame(width: 32, height: 32).contentShape(Rectangle())
    }
}

struct PosterBadge: View {
    let letter: String
    let color: Color
    let message: String
    var running = false
    var retry: (() -> Void)? = nil
    @State private var showing = false
    var body: some View {
        Button { showing.toggle() } label: { PosterBadgeFace(letter: letter, color: color, running: running) }
            .buttonStyle(.plain).help(message).accessibilityLabel("\(letter) · \(message)")
            .popover(isPresented: $showing, attachmentAnchor: .rect(.bounds), arrowEdge: .bottom) {
                VStack(alignment: .leading, spacing: 12) {
                    Text(message).font(.footnote).textSelection(.enabled)
                    if let retry {
                        Button("重新提取", systemImage: "arrow.clockwise") { showing = false; retry() }
                            .frame(minHeight: 44)
                    }
                }
                .padding(12).frame(width: 260, alignment: .leading)
                .fixedSize(horizontal: false, vertical: true)
                .presentationCompactAdaptation(.popover)
            }
    }
}

struct PageFooter: View {
    @ObservedObject var page: PageStore
    let load: () async -> Void
    var body: some View {
        if page.loading { HStack { Spacer(); ProgressView(); Spacer() } }
        else if page.rows.count < page.total {
            Button("加载更多（\(page.rows.count)/\(page.total)）") { Task { await load() } }
                .frame(maxWidth: .infinity)
        } else if !page.rows.isEmpty {
            Text("共 \(page.total) 条").font(.caption).foregroundStyle(.secondary).frame(maxWidth: .infinity)
        }
    }
}

struct JSONDetails: View {
    let value: JSONValue
    var body: some View {
        ForEach(value.object.keys.sorted(), id: \.self) { key in
            switch value[key] {
            case .array, .object:
                NavigationLink(fieldTitle(key)) { List { JSONDocument(value: value[key]) }.navigationTitle(fieldTitle(key)) }
            default:
                LabeledContent(fieldTitle(key)) {
                    Text(value[key].text.nonempty ?? "—").textSelection(.enabled).multilineTextAlignment(.trailing)
                }
            }
        }
    }
}

struct JSONDocument: View {
    let value: JSONValue
    var body: some View {
        switch value {
        case .object: JSONDetails(value: value)
        case .array(let items):
            ForEach(items.indices, id: \.self) { index in
                Section("\(index + 1)") { JSONDocument(value: items[index]) }
            }
        default: Text(value.text.nonempty ?? "—").textSelection(.enabled)
        }
    }
}

struct ServerDocumentView: View {
    @EnvironmentObject private var store: AppStore
    let title: String
    let path: String
    @State private var document: JSONValue = .null
    var body: some View {
        List { JSONDocument(value: document) }.navigationTitle(title)
            .task { await load() }.refreshable { await load() }
    }
    private func load() async {
        do { document = try await store.client.get(path, diagnostic: path == "health") } catch { store.report(error) }
    }
}

struct OperationNotice: View {
    @EnvironmentObject private var store: AppStore
    var body: some View {
        if let message = store.error ?? store.notice {
            HStack(alignment: .top) {
                Label(message, systemImage: store.error == nil ? "checkmark.circle" : "exclamationmark.circle")
                    .font(.footnote).foregroundStyle(store.error == nil ? Color.primary : .red)
                Spacer()
                Button { store.error = nil; store.notice = nil } label: { Image(systemName: "xmark.circle.fill") }.accessibilityLabel("关闭提示")
            }.padding(12).background(.regularMaterial)
        }
    }
}
