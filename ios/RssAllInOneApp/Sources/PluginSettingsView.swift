import SwiftUI

struct PluginSettingsView: View {
    @EnvironmentObject private var store: AppStore
    @State private var draft: JSONValue = .null
    @State private var original: JSONValue = .null
    @State private var loaded = false
    @State private var confirming = false
    var body: some View {
        Form {
            if loaded {
                Section("基本设置") {
                    ForEach(["enabled", "inventory_root", "pending_import_cron"], id: \.self) { field in
                        if draft.object[field] != nil { ValueField(key: field, value: binding(field)) }
                    }
                }
                Section("目录") {
                    if draft.object["source_routes"] != nil { ValueField(key: "source_routes", value: binding("source_routes")) }
                }
                Section("服务与高级设置") {
                    ValueFields(value: $draft, excluded: ["enabled", "inventory_root", "pending_import_cron", "source_routes", "database_filename"])
                }
            } else { ProgressView().frame(maxWidth: .infinity) }
        }
        .navigationTitle("插件设置")
        .toolbar { Button("保存") { confirming = true }.disabled(!loaded || store.busy || draft == original) }
        .confirmationDialog("保存配置并重新初始化插件？", isPresented: $confirming, titleVisibility: .visible) {
            Button("保存") { Task { await save() } }
        } message: { Text("当前插件任务可能会中断，请先确认没有正在执行的入库操作。") }
        .task { await load() }
    }
    private func binding(_ key: String) -> Binding<JSONValue> { Binding(get: { draft[key] }, set: { draft[key] = $0 }) }
    private func load() async {
        do {
            original = try await store.client.get("plugin/RssAllInOne", plugin: false)
            draft = original; loaded = true
        } catch { store.report(error) }
    }
    private func save() async {
        do {
            let latest = try await store.client.get("plugin/RssAllInOne", plugin: false)
            guard latest == original else { throw APIError.server("服务器配置已发生变化，请返回设置页重新读取后再保存") }
            if await store.perform("plugin/RssAllInOne", body: draft, method: "PUT", plugin: false) != nil { original = draft }
        } catch { store.report(error) }
    }
}

struct MaintenanceView: View {
    @EnvironmentObject private var store: AppStore
    @State private var action = ""
    @State private var confirm = ""
    @State private var show = false
    @State private var tasks: [Record] = []
    @State private var taskID = ""
    var body: some View {
        Form {
            Section("卡片") {
                Button("清空所有 qB 与入库卡片", role: .destructive) { action = "clear"; show = true }
            }
            Section("手动添加任务") {
                Picker("任务", selection: $taskID) {
                    Text("请选择").tag("")
                    ForEach(tasks) { Text($0.title).tag($0.id) }
                }
                Button("修复存量元数据") { action = "repair"; show = true }.disabled(taskID.isEmpty)
                Button("修复存量国配分类") { action = "mandarin"; show = true }.disabled(taskID.isEmpty)
                Button("清理任务的 qB 数据库记录", role: .destructive) { action = "task_clear"; show = true }.disabled(taskID.isEmpty)
            }
        }
        .navigationTitle("数据维护")
        .task {
            do {
                tasks = try await store.client.allTasks()
                    .filter { $0["config"]["task_type"].text == "manual" }.map { Record(value: $0) }
            } catch { store.report(error) }
        }
        .alert("确认数据维护操作", isPresented: $show) {
            TextField("输入 CONFIRM", text: $confirm).textInputAutocapitalization(.characters)
            Button("取消", role: .cancel) { confirm = "" }
            Button("执行", role: action.contains("clear") ? .destructive : nil) {
                guard confirm == "CONFIRM" else { store.error = "确认文字不正确，未执行"; confirm = ""; return }
                confirm = ""
                Task { await run() }
            }
        } message: {
            Text(action == "clear" ? "清空插件卡片，不删除媒体文件。请输入 CONFIRM。" : "此操作会修改所选手动任务的记录；元数据修复会修改文件名称。请输入 CONFIRM。")
        }
        .disabled(store.busy)
    }
    private func run() async {
        switch action {
        case "clear": await store.perform("data/clear-cards", body: .object(["confirm": .string("CLEAR")]))
        case "repair": await store.perform("rss/run", body: .object(["task_id": .string(taskID), "run_mode": .string("repair")]))
        case "mandarin": await store.perform("data/repair-manual-mandarin", body: .object(["task_id": .string(taskID)]))
        default: await store.perform("data/clear-task-records", body: .object(["task_id": .string(taskID), "confirm": .string("CLEAR_MANUAL_TASK")]))
        }
    }
}
