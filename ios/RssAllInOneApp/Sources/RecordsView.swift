import SwiftUI

struct RecordsView: View {
    @EnvironmentObject private var store: AppStore
    let qb: Bool
    @StateObject private var page = PageStore()
    @State private var state = ""
    @State private var mediaType = ""
    @State private var downloader = ""
    @State private var taskIDs: Set<String> = []
    @State private var options: [Record] = []
    @State private var search = ""
    @State private var editing = false
    @State private var selected: Set<String> = []
    @State private var action = ""
    @State private var confirming = false
    @State private var showFilters = false
    @State private var expandedSourceIDs: Set<String> = []

    private var filterKey: String { "\(state)|\(mediaType)|\(downloader)|\(taskIDs.sorted())|\(qb ? search : "")|\(store.generation)" }
    private var selectedRows: [Record] { page.rows.filter { selected.contains($0.id) } }
    private var states: [String] { qb ? ["", "pending", "existing", "recognized", "unrecognized"] : ["", "identified", "unidentified", "existing", "pending", "imported", "rolled_back"] }
    private var visible: [Record] {
        qb || search.isEmpty ? page.rows : page.rows.filter { $0.title.localizedCaseInsensitiveContains(search) || $0.source.localizedCaseInsensitiveContains(search) }
    }
    private var query: [URLQueryItem] {
        qb ? [
            .init(name: "view", value: state), .init(name: "downloader_id", value: downloader),
            .init(name: "keyword", value: search)
        ] : [
            .init(name: "state", value: state), .init(name: "media_type", value: mediaType),
            .init(name: "rss_task_ids", value: taskIDs.sorted().joined(separator: ","))
        ]
    }

    var body: some View {
        NavigationStack {
            List {
                Section {
                    Picker("状态", selection: $state) {
                        ForEach(states, id: \.self) { Text(filterTitle($0)).tag($0) }
                    }
                    .pickerStyle(.menu)
                }
                Section {
                    ForEach(visible) { item in
                        HStack(alignment: .top, spacing: 8) {
                            if editing {
                                Button {
                                    if !selected.insert(item.id).inserted { selected.remove(item.id) }
                                } label: { Image(systemName: selected.contains(item.id) ? "checkmark.circle.fill" : "circle").font(.title2) }
                                .buttonStyle(.plain).accessibilityLabel(selected.contains(item.id) ? "取消选择" : "选择")
                            }
                            RecordRow(item: item, qb: qb, interactive: true,
                                      sourceExpanded: expandedSourceIDs.contains(item.id)) {
                                if !expandedSourceIDs.insert(item.id).inserted {
                                    expandedSourceIDs.remove(item.id)
                                }
                            }
                            if !editing {
                                RecordActions(item: item, qb: qb) { action in
                                    selected = [item.id]
                                    self.action = action
                                    confirming = true
                                }
                            }
                        }
                        .padding(.vertical, 2)
                        .listRowInsets(EdgeInsets(top: 2, leading: 16, bottom: 2, trailing: 12))
                    }
                    PageFooter(page: page) { await load(more: true) }
                }
                if page.rows.isEmpty && !page.loading { ContentUnavailableView("暂无记录", systemImage: qb ? "arrow.down.circle" : "archivebox") }
            }
            .navigationTitle(qb ? "qB 管理" : "入库管理")
            .searchable(text: $search, prompt: qb ? "搜索任务" : "搜索已加载的媒体")
            .listSectionSpacing(.compact)
            .listRowSpacing(0)
            .toolbar {
                ToolbarItemGroup(placement: .topBarTrailing) {
                    Button { showFilters = true } label: { Image(systemName: "line.3.horizontal.decrease.circle") }.accessibilityLabel("筛选")
                    Menu {
                        Button(editing ? "结束选择" : "选择卡片", systemImage: "checkmark.circle") { editing.toggle(); selected.removeAll() }
                        if editing {
                            Button("全选已加载记录", systemImage: "checkmark.circle.fill") { selected = Set(page.rows.map(\.id)) }
                        }
                        if qb {
                            Button("核对待下载任务", systemImage: "checkmark.magnifyingglass") { action = "presence"; confirming = true }
                            Button("刷新识别 qB 任务", systemImage: "arrow.clockwise") { action = "refresh_qb"; confirming = true }
                        } else {
                            Button("立刻处理待入库", systemImage: "play.circle") { action = "run_pending"; confirming = true }
                        }
                        Button("刷新列表", systemImage: "arrow.clockwise") { Task { await load() } }
                    } label: { Image(systemName: "ellipsis.circle") }
                    .accessibilityIdentifier(qb ? "qbActions" : "mediaActions")
                }
            }
            .safeAreaInset(edge: .bottom) {
                VStack(spacing: 0) {
                    if editing && !selected.isEmpty { selectionBar }
                }
            }
            .sheet(isPresented: $showFilters) { filters }
            .confirmationDialog(actionTitle, isPresented: $confirming, titleVisibility: .visible) {
                Button(actionTitle, role: destructive ? .destructive : nil) { Task { await runAction() } }
                Button("取消", role: .cancel) {}
            } message: { Text(actionMessage) }
            .refreshable { await load() }
            .task(id: filterKey) {
                selected.removeAll()
                if qb { try? await Task.sleep(for: .milliseconds(250)) }
                guard !Task.isCancelled else { return }
                await load()
            }
            .task { await loadOptions() }
            .disabled(store.busy)
        }
    }

    private var selectionBar: some View {
        HStack {
            Text("已选 \(selected.count) 项").font(.footnote)
            Spacer()
            Menu {
                if qb {
                    Button("删除 qB 任务，保留文件") { action = "delete_qb"; confirming = true }
                } else {
                    if selectedRows.allSatisfy({ ["identified", "rolled_back"].contains($0.state) }) {
                        Button("转待入库") { action = "queue_import"; confirming = true }
                    }
                    if selectedRows.allSatisfy({ ["identified", "pending", "rolled_back"].contains($0.state) }) {
                        Button("入库") { action = "import"; confirming = true }
                    }
                    if selectedRows.allSatisfy({ $0.state == "imported" }) {
                        Button("复查库存") { action = "inventory"; confirming = true }
                    }
                    if selectedRows.allSatisfy({ $0.state != "imported" && $0.state != "importing" }) {
                        Button("删除源文件", role: .destructive) { action = "delete_source"; confirming = true }
                    }
                    Button("只删除插件硬链接", role: .destructive) { action = "delete_hardlinks"; confirming = true }
                    Button("删除硬链接和源文件", role: .destructive) { action = "delete_both"; confirming = true }
                }
            } label: { Label("批量操作", systemImage: "ellipsis.circle") }
        }.padding().background(.regularMaterial)
    }

    private var filters: some View {
        NavigationStack {
            Form {
                if qb {
                    Picker("下载器", selection: $downloader) {
                        Text("全部").tag("")
                        ForEach(options) { Text($0["name"].text).tag($0["name"].text) }
                    }
                } else {
                    Picker("媒体类型", selection: $mediaType) {
                        Text("全部").tag(""); Text("电影").tag("movie"); Text("剧集").tag("tv")
                    }
                    Section("RSS / 手动添加任务") {
                        ForEach(options) { option in
                            Toggle(option.title, isOn: Binding(
                                get: { taskIDs.contains(option.id) },
                                set: { if $0 { taskIDs.insert(option.id) } else { taskIDs.remove(option.id) } }
                            ))
                        }
                    }
                }
                Button("重置筛选") { downloader = ""; mediaType = ""; taskIDs.removeAll(); state = "" }
            }
            .navigationTitle("筛选")
            .toolbar { Button("完成") { showFilters = false } }
        }.presentationDetents([.medium, .large])
    }

    private var actionTitle: String {
        [
            "presence": "核对待下载任务", "refresh_qb": "刷新识别 qB 任务", "run_pending": "立刻处理待入库",
            "delete_qb": "删除 qB 任务", "queue_import": "转待入库", "import": "入库",
            "inventory": "复查库存", "delete_source": "删除源文件", "delete_hardlinks": "只删除插件硬链接",
            "delete_both": "删除硬链接和源文件"
        ][action] ?? "执行操作"
    }
    private var destructive: Bool { action.hasPrefix("delete") }
    private var actionMessage: String {
        if action == "presence" { return "按当前下载器和搜索条件核对待下载任务，仅删除 qB 中已不存在的卡片。" }
        if action == "delete_qb" { return "删除选中的 \(selected.count) 个 qB 任务，保留下载文件。" }
        if action == "delete_source" { return "永久删除选中卡片映射的源文件并移除卡片，保留硬链接。" }
        if action == "delete_both" { return "永久删除源文件和本插件拥有的硬链接，无法撤销。" }
        if action == "delete_hardlinks" { return "删除本插件拥有的硬链接，源文件保留，卡片回退。" }
        return selected.isEmpty ? "确认执行\(actionTitle)？" : "对选中的 \(selected.count) 项执行\(actionTitle)？"
    }
    private func filterTitle(_ value: String) -> String {
        if value.isEmpty { return "全部" }
        if qb { return ["pending": "待下载", "existing": "已存在", "recognized": "已识别", "unrecognized": "未识别"][value] ?? value }
        return statusText(value)
    }
    private func load(more: Bool = false) async {
        do { try await page.load(store.client, path: qb ? "torrents" : "media", query: query, more: more) }
        catch { store.report(error) }
    }
    private func loadOptions() async {
        do {
            let values: [JSONValue]
            if qb { values = try await store.client.get("qb/downloaders")["items"].array }
            else { values = try await store.client.allTasks() }
            options = values.map { Record(value: $0) }
        } catch { store.report(error) }
    }
    private func runAction() async {
        let ids = JSONValue.strings(selectedRows.map(\.id))
        switch action {
        case "presence": await store.perform("qb/check-presence", body: .object(["downloader_id": .string(downloader), "keyword": .string(search)]))
        case "refresh_qb": await store.perform("qb/refresh", body: .object(["force_recognition": .bool(true)]))
        case "run_pending": await store.perform("import/run")
        case "delete_qb": await store.perform("qb/delete", body: .object(["items": .array(selectedRows.map(\.identityPayload))]))
        case "inventory": await store.perform("media/inventory/refresh-batch", body: .object(["media_ids": ids]))
        default:
            var body: JSONValue = .object(["action": .string(action), "media_ids": ids])
            if destructive { body["confirm"] = .string("CONFIRM_" + action.uppercased()) }
            await store.perform("media/action", body: body)
        }
        selected.removeAll()
        await load()
    }
}

struct RecordActions: View {
    let item: Record
    let qb: Bool
    let onAction: (String) -> Void

    private var mediaCanQueue: Bool { ["identified", "rolled_back"].contains(item.state) }
    private var mediaCanImport: Bool { ["identified", "pending", "rolled_back"].contains(item.state) }
    private var mediaCanDeleteSource: Bool { !["imported", "importing"].contains(item.state) }

    var body: some View {
        VStack(alignment: .trailing, spacing: 4) {
            if qb {
                actionButton("删任务", systemImage: "trash", action: "delete_qb", destructive: true)
            } else {
                if mediaCanQueue { actionButton("转待入库", systemImage: "tray.and.arrow.down", action: "queue_import") }
                if mediaCanImport { actionButton("入库", systemImage: "archivebox", action: "import") }
                if mediaCanDeleteSource { actionButton("删源", systemImage: "trash", action: "delete_source", destructive: true) }
            }
        }
        .frame(width: 86, alignment: .trailing)
        .accessibilityElement(children: .contain)
    }

    @ViewBuilder
    private func actionButton(_ title: String, systemImage: String, action: String, destructive: Bool = false) -> some View {
        if destructive {
            Button(role: .destructive) { onAction(action) } label: {
                Image(systemName: systemImage)
                    .frame(width: 30, height: 30)
            }
            .buttonStyle(.bordered)
            .controlSize(.mini)
            .accessibilityLabel(title)
            .help(title)
        } else {
            Button { onAction(action) } label: {
                Image(systemName: systemImage)
                    .frame(width: 30, height: 30)
            }
            .buttonStyle(.bordered)
            .controlSize(.mini)
            .accessibilityLabel(title)
            .help(title)
        }
    }
}

struct RecordDetailView: View {
    @EnvironmentObject private var store: AppStore
    @Environment(\.dismiss) private var dismiss
    let item: Record
    let qb: Bool
    @State private var identify = false
    @State private var delete = false
    private var mutable: Bool { qb || !["imported", "importing"].contains(item.state) }
    private var canMove: Bool {
        qb ? ["identified", "error"].contains(item["recognition_state"].text) : ["identified", "existing", "rolled_back"].contains(item.state)
    }
    var body: some View {
        List {
            Section { RecordRow(item: item, qb: qb) }
            if !item.failure.isEmpty { Section("处理异常") { Text(item.failure).foregroundStyle(.red).textSelection(.enabled) } }
            if item.labels["status"].text == "failed" {
                Section("站点标签") { Text(item.labels["reason"].text).foregroundStyle(.orange) }
            }
            Section("来源") {
                if let link = item.sourceURL { Link(destination: link) { Label("P · 种子页面", systemImage: "link") } }
                if let link = item.tmdbURL { Link(destination: link) { Label("T · TMDB", systemImage: "film") } }
                Text(item.source).font(.footnote).textSelection(.enabled)
                if !item["info_hash"].text.isEmpty { LabeledContent("种子哈希", value: item["info_hash"].text).font(.caption).textSelection(.enabled) }
            }
            Section("操作") {
                if item.state != "importing" {
                    Button(item.state == "imported" ? "复查库存" : "重新识别及复查库存", systemImage: "arrow.clockwise") {
                        Task {
                            let result = await store.perform(qb ? "qb/item/refresh" : "media/refresh", body: qb ? item.identityPayload : .object(["media_id": .string(item.id)]))
                            if result != nil { dismiss() }
                        }
                    }
                }
                if mutable { Button("编辑识别与标签", systemImage: "pencil") { identify = true } }
                if canMove {
                    Button("移入未识别", systemImage: "questionmark.folder") {
                        Task {
                            if await store.perform("media/mark-unidentified", body: qb ? item.identityPayload : .object(["media_id": .string(item.id)])) != nil { dismiss() }
                        }
                    }
                }
                if !qb && item.state == "pending" { Button("删除卡片记录", role: .destructive) { delete = true } }
            }
            Section("媒体和文件") { JSONDetails(value: item.value) }
        }
        .navigationTitle(item.title).navigationBarTitleDisplayMode(.inline)
        .disabled(store.busy)
        .sheet(isPresented: $identify, onDismiss: {}) { IdentifyView(item: item) { dismiss() } }
        .confirmationDialog("仅删除此卡片记录，保留文件？", isPresented: $delete, titleVisibility: .visible) {
            Button("删除卡片记录", role: .destructive) {
                Task { if await store.perform("media/delete", body: .object(["media_id": .string(item.id)])) != nil { dismiss() } }
            }
        }
    }
}

struct IdentifyView: View {
    @EnvironmentObject private var store: AppStore
    @Environment(\.dismiss) private var dismiss
    let item: Record
    let onSaved: () -> Void
    @State private var type = "tv"
    @State private var tmdb = ""
    @State private var season = "1"
    @State private var category = ""
    @State private var mandarin = false
    @State private var effects = false
    @State private var categories: [String] = []

    var body: some View {
        NavigationStack {
            Form {
                Section { Text(item.title).font(.headline) }
                Section("媒体") {
                    Picker("类型", selection: $type) { Text("电影").tag("movie"); Text("剧集").tag("tv") }.pickerStyle(.segmented)
                    TextField("TMDB ID", text: $tmdb).keyboardType(.numberPad)
                    if type == "tv" { TextField("季号（特别篇填 0）", text: $season).keyboardType(.numberPad) }
                    Picker("分类", selection: $category) {
                        Text("自动分类").tag("")
                        ForEach(categories, id: \.self) { Text($0).tag($0) }
                    }
                }
                Section("标签") { Toggle("国配", isOn: $mandarin); Toggle("特效", isOn: $effects) }
            }
            .navigationTitle("编辑识别")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("取消") { dismiss() }.disabled(store.busy) }
                ToolbarItem(placement: .confirmationAction) {
                    Button("确认") { Task { await save() } }
                        .disabled(store.busy || (Int(tmdb) ?? 0) <= 0 || (type == "tv" && (Int(season) ?? -1) < 0))
                }
            }
            .interactiveDismissDisabled(store.busy)
            .safeAreaInset(edge: .bottom) { OperationNotice() }
            .task {
                type = item["media_type"].text == "movie" ? "movie" : "tv"
                tmdb = item["tmdb_id"].text
                season = item["season"].text.nonempty ?? "1"
                category = item.details["manual_override"]["category"].text
                mandarin = item.labels["mandarin"].flag; effects = item.labels["effects"].flag
                do {
                    categories = try await store.client.get("categories")["items"].array.map(\.text)
                    if !category.isEmpty && !categories.contains(category) { categories.append(category) }
                } catch { store.report(error) }
            }
        }
    }
    private func save() async {
        var payload = item.identityPayload
        if !item["id"].text.isEmpty { payload["media_id"] = .string(item.id) }
        payload["media_type"] = .string(type); payload["tmdb_id"] = .number(Double(Int(tmdb) ?? 0))
        payload["season"] = type == "tv" ? .number(Double(Int(season) ?? 0)) : .null
        payload["category"] = .string(category)
        payload["manual_labels"] = .object(["source": .string("manual"), "manual_override": .bool(true),
                                          "mandarin": .bool(mandarin), "effects": .bool(effects)])
        if await store.perform("qb/item/identify", body: payload) != nil { dismiss(); onSaved() }
    }
}
