import SwiftUI

struct RSSView: View {
    @EnvironmentObject private var store: AppStore
    @State private var tasks: [Record] = []
    @State private var editing: Record?
    @State private var loading = false
    @State private var snapshot: [JSONValue] = []
    @State private var deleteID: String?

    var body: some View {
        NavigationStack {
            List {
                Section {
                    Toggle("RSS 调度", isOn: Binding(
                        get: { store.overview["plugin"]["rss_enabled"].flag },
                        set: { next in Task { await store.perform("rss/control", body: .object(["enabled": .bool(next)])) } }
                    )).disabled(store.busy)
                }
                ForEach(tasks) { task in
                    Section {
                        Button { editing = task } label: {
                            HStack {
                                Image(systemName: task["config"]["task_type"].text == "manual" ? "hand.point.up.left" : "dot.radiowaves.left.and.right")
                                    .foregroundStyle(.teal).frame(width: 28)
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(task.title).font(.headline).foregroundStyle(.primary)
                                    Text([task["config"]["qb_downloader"].text, task["config"]["qb_category"].text].filter { !$0.isEmpty }.joined(separator: " · "))
                                        .font(.caption).foregroundStyle(.secondary)
                                }
                                Spacer()
                                Image(systemName: task["enabled"].flag ? "checkmark.circle.fill" : "pause.circle").foregroundStyle(.secondary)
                            }
                        }.buttonStyle(.plain)
                        Menu {
                            Button("测试配置", systemImage: "checkmark.magnifyingglass") {
                                Task { await store.perform("rss/test", body: .object(["task": task.value])) }
                            }
                            Button(task["config"]["task_type"].text == "manual" ? "自动处理剩余项目" : "立即执行", systemImage: "play") {
                                run(task, mode: "all")
                            }
                            if task["config"]["task_type"].text == "manual" {
                                Button("试跑一条", systemImage: "forward.end") { run(task, mode: "single") }
                                Button("停止当前处理", systemImage: "stop") {
                                    Task { await store.perform("rss/manual/stop", body: .object(["task_id": store.overview["manual_task"]["id"]])) }
                                }
                            }
                            Button("删除任务配置", systemImage: "trash", role: .destructive) { deleteID = task.id }
                        } label: { Label("执行操作", systemImage: "ellipsis.circle") }
                    }
                }
                if loading { ProgressView().frame(maxWidth: .infinity) }
                if tasks.isEmpty && !loading { ContentUnavailableView("暂无 RSS 任务", systemImage: "dot.radiowaves.left.and.right") }
            }
            .navigationTitle("RSS 任务")
            .toolbar {
                Button { editing = Record(value: TaskDefaults.newTask) } label: { Image(systemName: "plus") }.accessibilityLabel("添加任务")
            }
            .task(id: store.generation) { await load() }
            .refreshable { await load() }
            .sheet(item: $editing) { item in
                TaskEditorView(original: item.value, snapshot: snapshot) { await load() }
            }
            .confirmationDialog("删除这条任务配置？", isPresented: Binding(get: { deleteID != nil }, set: { if !$0 { deleteID = nil } }), titleVisibility: .visible) {
                Button("删除任务配置", role: .destructive) {
                    let target = deleteID
                    Task {
                        await saveTasks(snapshot.filter { $0["id"].text != target })
                        deleteID = nil
                    }
                }
            } message: { Text("保留已有媒体卡片和文件。") }
            .safeAreaInset(edge: .bottom) { OperationNotice() }
        }
    }

    private func run(_ task: Record, mode: String) {
        Task { await store.perform("rss/run", body: .object(["task_id": .string(task.id), "run_mode": .string(mode)])) }
    }
    private func load() async {
        loading = true; defer { loading = false }
        do {
            var values: [JSONValue] = []
            while true {
                let result = try await store.client.get("rss/tasks", query: [.init(name: "offset", value: String(values.count)), .init(name: "limit", value: "200")])
                let batch = result["items"].array
                values += batch
                if batch.isEmpty || values.count >= result["total"].int { break }
            }
            snapshot = values; tasks = values.map { Record(value: $0) }
        } catch { store.report(error) }
    }
    private func saveTasks(_ values: [JSONValue]) async {
        do {
            let current = try await store.client.get("rss/tasks", query: [.init(name: "limit", value: "200")])
            guard current["items"].array == snapshot else { throw APIError.server("服务器任务已发生变化，请刷新后再删除") }
            await store.perform("rss/tasks", body: .object(["items": .array(values)]))
            await load()
        } catch { store.report(error) }
    }
}

struct TaskEditorView: View {
    @EnvironmentObject private var store: AppStore
    @Environment(\.dismiss) private var dismiss
    let original: JSONValue
    let snapshot: [JSONValue]
    let saved: () async -> Void
    @State private var draft: JSONValue = .object([:])
    @State private var downloaders: [Record] = []
    @State private var sites: [Record] = []

    var body: some View {
        NavigationStack {
            Form {
                Section("任务") {
                    ValueField(key: "name", value: binding("name"))
                    ValueField(key: "enabled", value: binding("enabled"))
                    Picker("类型", selection: configString("task_type")) {
                        Text("RSS").tag("rss"); Text("手动添加").tag("manual")
                    }
                    Picker("qB 下载器", selection: configString("qb_downloader")) {
                        Text("请选择").tag("")
                        ForEach(downloaders) { Text($0["name"].text).tag($0["name"].text) }
                    }
                    Picker("站点", selection: configString("site_id")) {
                        Text("不使用站点").tag("")
                        ForEach(sites) { Text($0["name"].text).tag($0["id"].text) }
                    }
                }
                Section("处理设置") {
                    ValueFields(value: binding("config"), excluded: [
                        "task_type", "qb_downloader", "site_id", "local_initialized", "local_initialized_at", "local_path_fingerprint"
                    ])
                }
                Section {
                    Button("测试当前配置", systemImage: "checkmark.magnifyingglass") {
                        Task { await store.perform("rss/test", body: .object(["task": draft])) }
                    }
                }
            }
            .navigationTitle("任务配置")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("取消") { dismiss() }.disabled(store.busy) }
                ToolbarItem(placement: .confirmationAction) { Button("保存") { Task { await save() } }.disabled(store.busy || draft["name"].text.isEmpty) }
            }
            .interactiveDismissDisabled(store.busy)
            .task {
                draft = original
                draft["config"] = .object(TaskDefaults.config.object.merging(original["config"].object) { _, new in new })
                do {
                    downloaders = try await store.client.get("qb/downloaders")["items"].array.map { Record(value: $0) }
                    sites = try await store.client.get("sites")["items"].array.map { Record(value: $0) }
                } catch { store.report(error) }
            }
        }
    }

    private func binding(_ key: String) -> Binding<JSONValue> {
        Binding(get: { draft[key] }, set: { draft[key] = $0 })
    }
    private func configString(_ key: String) -> Binding<String> {
        Binding(get: { draft["config"][key].text }, set: { new in
            var config = draft["config"]; config[key] = .string(new); draft["config"] = config
        })
    }
    private func save() async {
        do {
            let current = try await store.client.get("rss/tasks", query: [.init(name: "limit", value: "200")])
            guard current["items"].array == snapshot else { throw APIError.server("服务器任务已发生变化，请关闭编辑页并刷新后重试") }
            var values = snapshot
            if let index = values.firstIndex(where: { $0["id"] == original["id"] }) { values[index] = draft }
            else { draft["position"] = .number(Double(values.count)); values.append(draft) }
            if await store.perform("rss/tasks", body: .object(["items": .array(values)])) != nil { await saved(); dismiss() }
        } catch { store.report(error) }
    }
}
