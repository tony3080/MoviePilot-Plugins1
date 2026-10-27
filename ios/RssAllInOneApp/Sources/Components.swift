import SwiftUI

struct StatusBadge: View {
    let state: String
    private var color: Color {
        if ["failed", "error", "unidentified", "rolled_back"].contains(state) { return .red }
        if ["completed", "succeeded", "imported", "exists", "existing"].contains(state) { return .green }
        if ["pending", "pending_import"].contains(state) { return .purple }
        if ["running", "importing", "queued"].contains(state) { return .orange }
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
    var body: some View {
        AsyncImage(url: safeWebURL(path)) { image in image.resizable().scaledToFill() } placeholder: {
            Rectangle().fill(Color.secondary.opacity(0.12)).overlay { Image(systemName: "film").foregroundStyle(.secondary) }
        }
        .frame(width: 64, height: 96).clipped().clipShape(RoundedRectangle(cornerRadius: 6))
        .accessibilityHidden(true)
    }
}

struct RecordRow: View {
    let item: Record
    let qb: Bool
    var interactive = false
    var sourceExpanded = false
    var onToggleSource: (() -> Void)? = nil

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Poster(path: item.poster)
            VStack(alignment: .leading, spacing: 4) {
                if interactive {
                    NavigationLink { RecordDetailView(item: item, qb: qb) } label: {
                        summary
                    }
                    .buttonStyle(.plain)
                } else {
                    summary
                }
                if let onToggleSource {
                    Button(action: onToggleSource) {
                        Label(sourceExpanded ? "隐藏源文件名" : "源文件名",
                              systemImage: sourceExpanded ? "chevron.up" : "doc.text")
                    }
                    .buttonStyle(.borderless)
                    .font(.caption2)
                    .foregroundStyle(.tint)
                    if sourceExpanded {
                        Text(item.sourceFileName)
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                            .lineLimit(3)
                            .textSelection(.enabled)
                    }
                }
            }
            .frame(maxWidth: .infinity, minHeight: 96, alignment: .topLeading)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    @ViewBuilder private var summary: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(item.title).font(.headline).lineLimit(2)
            BadgeFlowLayout { rowLabels }
            if !item.inventorySummary.isEmpty {
                Text(item.inventorySummary)
                    .font(.caption2.weight(.medium))
                    .foregroundStyle(inventoryColor)
                    .padding(.top, 1)
            }
            if qb {
                ProgressView(value: min(1, max(0, item["progress"].double))).tint(.teal)
                Text("\(Int(item["progress"].double * 100))%")
                    .font(.caption2).foregroundStyle(.secondary)
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
        StatusBadge(state: qb ? item["recognition_state"].text : item.state)
        if !item["season"].text.isEmpty { InfoBadge(text: "S\(item["season"].text)", color: .purple) }
        if !item.resolution.isEmpty { InfoBadge(text: item.resolution, color: .cyan) }
        if !item.mediaCategory.isEmpty { InfoBadge(text: item.mediaCategory, color: .purple) }
        if !item.customization.isEmpty { InfoBadge(text: item.customization, color: .teal) }
        let bytes = item["size"].double > 0 ? item["size"].double : item.details["torrent"]["size"].double
        if bytes > 0 { InfoBadge(text: sizeText(bytes), color: .secondary) }
        if item.labels["mandarin"].flag { InfoBadge(text: "国配", color: .red) }
        if item.labels["effects"].flag { InfoBadge(text: "特效", color: .teal) }
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
