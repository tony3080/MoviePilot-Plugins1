import SwiftUI

struct StatusBadge: View {
    let state: String
    private var color: Color {
        if ["failed", "error", "unidentified", "rolled_back"].contains(state) { return .red }
        if ["completed", "imported", "exists", "existing"].contains(state) { return .green }
        if ["running", "pending", "importing", "queued"].contains(state) { return .orange }
        return .blue
    }
    var body: some View {
        Text(statusText(state)).font(.caption.weight(.medium)).foregroundStyle(color)
            .padding(.horizontal, 7).padding(.vertical, 4).background(color.opacity(0.1), in: RoundedRectangle(cornerRadius: 5))
    }
}

struct Poster: View {
    let path: String
    var body: some View {
        AsyncImage(url: safeWebURL(path)) { image in image.resizable().scaledToFill() } placeholder: {
            Rectangle().fill(Color.secondary.opacity(0.12)).overlay { Image(systemName: "film").foregroundStyle(.secondary) }
        }
        .frame(width: 56, height: 84).clipped().clipShape(RoundedRectangle(cornerRadius: 5))
        .accessibilityHidden(true)
    }
}

struct RecordRow: View {
    let item: Record
    let qb: Bool
    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Poster(path: item.poster)
            VStack(alignment: .leading, spacing: 5) {
                Text(item.title).font(.headline).lineLimit(2)
                Text([item["category"].text, item["season"].text.isEmpty ? "" : "S\(item["season"].text)"]
                    .filter { !$0.isEmpty }.joined(separator: " · ")).font(.caption).foregroundStyle(.secondary)
                HStack {
                    StatusBadge(state: qb ? item["recognition_state"].text : item.state)
                    if item.labels["mandarin"].flag { Text("国配").font(.caption).foregroundStyle(.red) }
                    if item.labels["effects"].flag { Text("特效").font(.caption).foregroundStyle(.teal) }
                }
                if qb {
                    ProgressView(value: min(1, max(0, item["progress"].double))).tint(.teal)
                    Text("\(Int(item["progress"].double * 100))% · \(statusText(item["inventory_state"].text))")
                        .font(.caption2).foregroundStyle(.secondary)
                }
                if !item.failure.isEmpty { Label(item.failure, systemImage: "exclamationmark.circle").font(.caption).foregroundStyle(.red).lineLimit(2) }
                if item.labels["status"].text == "failed" { Label("站点标签获取失败", systemImage: "tag.slash").font(.caption).foregroundStyle(.orange) }
            }
        }.padding(.vertical, 5)
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
        do { document = try await store.client.get(path) } catch { store.report(error) }
    }
}

struct OperationNotice: View {
    @EnvironmentObject private var store: AppStore
    var body: some View {
        if let message = store.notice {
            HStack(alignment: .top) {
                Text(message).font(.footnote)
                Spacer()
                Button { store.notice = nil } label: { Image(systemName: "xmark.circle.fill") }.accessibilityLabel("关闭提示")
            }.padding(12).background(.regularMaterial)
        }
    }
}
