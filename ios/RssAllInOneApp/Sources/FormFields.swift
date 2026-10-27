import SwiftUI

func fieldTitle(_ key: String) -> String {
    let titles = [
        "name": "名称", "enabled": "启用", "config": "配置", "id": "编号", "position": "排序",
        "rss_url": "RSS 链接", "task_type": "任务类型", "qb_downloader": "qB 下载器",
        "rss_cron": "Cron / 固定间隔（分钟）", "save_path": "下载保存路径", "qb_category": "qB 分类",
        "name_contains": "名称包含", "start_cron": "开始下载 Cron", "delete_after_minutes": "完成后删除任务（分钟）",
        "upload_limit_kbps": "上传限速（KB/s）", "rename_rules": "自定义识别词", "site_id": "站点",
        "cn_keywords": "国配关键词", "pause_on_add": "添加时暂停", "push_torrent_file": "推送种子文件",
        "recognize_cn": "识别国配", "recognize_fx": "识别特效", "add_chinese_title": "添加中文标题",
        "import_enabled": "入库", "realtime_hardlink_enabled": "完成后创建实时硬链接",
        "realtime_source_root": "实时硬链接源根目录", "realtime_link_root": "实时硬链接目标根目录",
        "rename_enabled": "重命名", "download_enabled": "下载", "delete_files": "删除文件", "hr_enabled": "HR 保护",
        "hr_cron": "HR 检查 Cron", "local_path": "本地目录", "process_local_files": "处理本地文件",
        "force_reprocess_local": "强制重新处理本地文件", "query_interval": "站点查询间隔（秒）",
        "database_filename": "数据库文件名", "inventory_root": "最终媒体库根目录",
        "source_routes": "源路径路由", "prefix": "源路径前缀", "link_roots": "本地硬链接根目录",
        "movie": "电影", "series": "剧集", "default": "默认", "cd2_grpc_addr": "CD2 gRPC 地址",
        "cd2_token": "CD2 令牌", "cd2_dest_root": "CD2 云端目标根目录",
        "pending_import_cron": "待入库 Cron", "cd2_discovery_timeout": "CD2 任务发现超时（秒）",
        "cd2_card_timeout": "CD2 卡片处理超时（秒）", "cd2_poll_interval": "CD2 轮询间隔（秒）",
        "cd2_transfer_grace": "CD2 真实传输宽限（秒）", "cd2_risk_cooldown": "CD2 风控冷却（秒）",
        "cd2_risk_retry_limit": "CD2 风控重试次数", "catchup_base_url": "追更服务地址",
        "catchup_page_id": "追更页面 ID", "catchup_token": "追更令牌",
        "scan_base_url": "SA 扫库地址", "scan_username": "SA 用户名", "scan_password": "SA 密码",
        "scan_setting_name": "SA 设置名称", "scan_target_name": "SA 目标名称",
        "emby_scan_base_url": "Emby 地址", "emby_scan_api_key": "Emby API Key",
        "scan_callback_secret": "扫库回调密钥", "scan_callback_server_name": "扫库节点名",
        "scan_callback_server_id": "扫库服务器 ID", "scan_callback_task_id": "扫库任务 ID",
        "scan_callback_task_name": "扫库任务名称", "scan_callback_timeout": "扫库回调超时（秒）",
        "rss_enabled": "RSS 调度", "media": "媒体记录", "torrents": "qB 快照", "rss_tasks": "RSS 任务",
        "import_watches": "CD2 监控", "background_tasks": "后台任务", "state": "状态",
        "task_type_name": "任务类型", "processed": "已处理", "total": "总数", "current_item": "当前项目",
        "error_message": "错误", "failure_message": "失败原因", "started_at": "开始时间",
        "finished_at": "结束时间", "created_at": "创建时间", "updated_at": "更新时间",
        "details": "详细信息", "result": "处理结果", "file_mappings": "文件映射",
        "source_path": "源路径", "current_source_path": "当前源路径", "local_hardlink_path": "本地硬链接",
        "inventory": "库存", "inventory_plan": "入库计划", "path_plan": "路径规划",
        "file_size": "文件大小", "size": "大小", "sha1": "SHA1", "title": "标题", "season": "季",
        "media_type": "媒体类型", "category": "分类", "source_name": "原始名称", "tmdb_id": "TMDB ID",
        "recognition": "识别结果", "manual_override": "人工识别", "site_labels": "站点标签",
        "running": "运行中", "pending": "待入库", "importing": "入库中", "active_watches": "活跃监控",
        "batch": "处理批次", "capabilities": "能力", "startup_error": "启动错误", "database": "数据库",
        "success": "成功", "enabled_count": "启用数", "failed": "失败数", "deleted": "已删除",
        "domain": "站点域名", "auth_mode": "认证方式", "ready": "就绪", "items": "记录",
        "comment_url": "来源链接", "source_url_masked": "来源链接", "downloader_id": "下载器",
        "info_hash": "种子哈希", "progress": "下载进度", "file_index": "文件序号",
        "source_identity": "文件来源", "import_control": "入库控制", "manual_labels": "人工标签"
    ]
    return titles[key] ?? key.replacingOccurrences(of: "_", with: " ")
}

struct ValueFields: View {
    @Binding var value: JSONValue
    var excluded: Set<String> = []
    var body: some View {
        ForEach(value.object.keys.filter { !excluded.contains($0) }.sorted(), id: \.self) { key in
            ValueField(key: key, value: Binding(get: { value[key] }, set: { value[key] = $0 }))
        }
    }
}

struct ValueField: View {
    let key: String
    @Binding var value: JSONValue
    private var secret: Bool { ["token", "password", "secret", "api_key"].contains { key.contains($0) } }

    var body: some View {
        switch value {
        case .bool:
            Toggle(fieldTitle(key), isOn: Binding(get: { value.flag }, set: { value = .bool($0) }))
        case .number:
            VStack(alignment: .leading, spacing: 4) {
                TextField(fieldTitle(key), value: Binding(get: { value.double }, set: { value = .number($0) }), format: .number.grouping(.never))
                    .keyboardType(.numbersAndPunctuation)
            }
        case .object:
            NavigationLink(fieldTitle(key)) { Form { ValueFields(value: $value) }.navigationTitle(fieldTitle(key)) }
        case .array:
            NavigationLink {
                ArrayFields(key: key, value: $value).navigationTitle(fieldTitle(key))
            } label: { LabeledContent(fieldTitle(key), value: "\(value.array.count)") }
        case .null:
            TextField(fieldTitle(key), text: Binding(get: { value.text }, set: { value = .string($0) }))
        case .string:
            VStack(alignment: .leading, spacing: 6) {
                Text(fieldTitle(key)).font(.caption).foregroundStyle(.secondary)
                if secret {
                    SecureField(fieldTitle(key), text: Binding(get: { value.text }, set: { value = .string($0) }))
                        .textInputAutocapitalization(.never).autocorrectionDisabled()
                } else {
                    TextField(fieldTitle(key), text: Binding(get: { value.text }, set: { value = .string($0) }), axis: .vertical)
                        .lineLimit(1...8).textInputAutocapitalization(.never).autocorrectionDisabled()
                }
            }.padding(.vertical, 3)
        }
    }
}

struct ArrayFields: View {
    let key: String
    @Binding var value: JSONValue
    var body: some View {
        Form {
            ForEach(value.array.indices, id: \.self) { index in
                Section("\(index + 1)") {
                    let binding = Binding<JSONValue>(
                        get: { value.array.indices.contains(index) ? value.array[index] : .null },
                        set: { new in
                            var items = value.array
                            guard items.indices.contains(index) else { return }
                            items[index] = new; value = .array(items)
                        }
                    )
                    if case .object = binding.wrappedValue { ValueFields(value: binding) }
                    else { ValueField(key: "name", value: binding) }
                    Button("删除此项", role: .destructive) { var items = value.array; items.remove(at: index); value = .array(items) }
                }
            }
            Button("添加", systemImage: "plus") {
                let first = value.array.first
                var items = value.array
                let route: JSONValue = .object([
                    "name": .string(""), "prefix": .string(""),
                    "enabled": .bool(true),
                    "link_roots": .object(["movie": .string(""), "series": .string(""), "default": .string("")])
                ])
                items.append(key == "source_routes" ? route : (first.map(blankValue) ?? .string("")))
                value = .array(items)
            }
        }
    }
    private func blankValue(_ source: JSONValue) -> JSONValue {
        switch source {
        case .object(let fields): return .object(fields.mapValues(blankValue))
        case .array: return .array([])
        case .bool: return .bool(false)
        case .number: return .number(0)
        default: return .string("")
        }
    }
}

enum TaskDefaults {
    static var config: JSONValue {
        .object([
            "task_type": .string("rss"), "rss_url": .string(""), "qb_downloader": .string(""),
            "rss_cron": .string("10"), "save_path": .string(""), "qb_category": .string(""),
            "name_contains": .string(""), "start_cron": .string("*/5 * * * *"),
            "delete_after_minutes": .number(0), "upload_limit_kbps": .number(0),
            "rename_rules": .string(""), "site_id": .string(""), "cn_keywords": .string("国语,国配"),
            "pause_on_add": .bool(true), "push_torrent_file": .bool(false),
            "recognize_cn": .bool(false), "recognize_fx": .bool(false), "add_chinese_title": .bool(false),
            "import_enabled": .bool(true), "realtime_hardlink_enabled": .bool(false),
            "realtime_source_root": .string(""), "realtime_link_root": .string(""),
            "rename_enabled": .bool(false), "download_enabled": .bool(true),
            "delete_files": .bool(false), "hr_enabled": .bool(false), "hr_cron": .string("30 3 * * *"),
            "local_path": .string(""), "process_local_files": .bool(false),
            "force_reprocess_local": .bool(false), "query_interval": .number(60)
        ])
    }
    static var newTask: JSONValue {
        .object(["id": .string(UUID().uuidString.replacingOccurrences(of: "-", with: "")),
                 "name": .string("新任务"), "enabled": .bool(true), "position": .number(0), "config": config])
    }
}
