import SwiftUI

struct PluginSettingsView: View {
    @EnvironmentObject private var store: AppStore
    @State private var draft: JSONValue = .null
    @State private var original: JSONValue = .null
    @State private var baseline: JSONValue = .null
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
        .toolbar { Button("保存") { confirming = true }.disabled(!loaded || store.busy || draft == baseline) }
        .confirmationDialog("保存配置并重新初始化插件？", isPresented: $confirming, titleVisibility: .visible) {
            Button("保存") { Task { await save() } }
        } message: { Text("当前插件任务可能会中断，请先确认没有正在执行的入库操作。") }
        .task { await load() }
    }
    private func binding(_ key: String) -> Binding<JSONValue> { Binding(get: { draft[key] }, set: { draft[key] = $0 }) }
    private func load() async {
        do {
            original = try await store.client.get("plugin/RssAllInOne", plugin: false)
            draft = PluginDefaults.normalized(original); baseline = draft; loaded = true
        } catch { store.report(error) }
    }
    private func save() async {
        do {
            let latest = try await store.client.get("plugin/RssAllInOne", plugin: false)
            guard latest == original else { throw APIError.server("服务器配置已发生变化，请返回设置页重新读取后再保存") }
            if await store.perform("plugin/RssAllInOne", body: draft, method: "PUT", plugin: false) != nil {
                original = draft; baseline = draft
            }
        } catch { store.report(error) }
    }
}

enum PluginDefaults {
    static func normalized(_ original: JSONValue) -> JSONValue {
        var result = value
        for (key, field) in original.object { result[key] = field }
        if case .string(let text) = result["source_routes"],
           let parsed = try? JSONDecoder().decode(JSONValue.self, from: Data(text.utf8)),
           case .array = parsed { result["source_routes"] = parsed }
        if case .array(let routes) = result["source_routes"] {
            result["source_routes"] = .array(routes.map { route in
                var copy = route
                if copy["enabled"] == .null { copy["enabled"] = .bool(true) }
                var roots: JSONValue = .object(["movie": .string(""), "series": .string(""), "default": .string("")])
                for (key, field) in copy["link_roots"].object { roots[key] = field }
                copy["link_roots"] = roots
                return copy
            })
        }
        return result
    }
    private static var value: JSONValue {
        var config: JSONValue = .object([
            "enabled": .bool(false), "rss_enabled": .bool(true),
            "inventory_root": .string("/SSD/云盘/strm/影视库"),
            "pending_import_cron": .string("0 1 * * *"),
            "cd2_discovery_timeout": .number(180), "cd2_card_timeout": .number(7200),
            "cd2_poll_interval": .number(10), "cd2_transfer_grace": .number(20),
            "cd2_risk_cooldown": .number(1800), "cd2_risk_retry_limit": .number(3),
            "scan_callback_timeout": .number(7200),
            "source_routes": .array([
                .object(["name": .string("UP"), "prefix": .string("/MP"), "enabled": .bool(true),
                         "link_roots": .object(["movie": .string("/MP/电影UP"), "series": .string("/MP/剧集UP")])]),
                .object(["name": .string("SSD"), "prefix": .string("/SSD"), "enabled": .bool(true),
                         "link_roots": .object(["default": .string("/SSD/云盘/l")])])
            ])
        ])
        for key in ["cd2_grpc_addr", "cd2_token", "cd2_dest_root", "catchup_base_url", "catchup_page_id",
                    "catchup_token", "scan_base_url", "scan_username", "scan_password", "scan_setting_name",
                    "scan_target_name", "emby_scan_base_url", "emby_scan_api_key", "scan_callback_secret",
                    "scan_callback_server_name", "scan_callback_server_id", "scan_callback_task_id", "scan_callback_task_name"] {
            config[key] = .string("")
        }
        return config
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
