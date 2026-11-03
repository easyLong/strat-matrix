CREATE TABLE IF NOT EXISTS godp_business_planning_config (
 config_key VARCHAR(32) NOT NULL PRIMARY KEY COMMENT '配置键，当前固定为operations',
 version INT NOT NULL COMMENT '当前业务配置版本号',
 planning_days VARCHAR(32) NOT NULL COMMENT '每周策划日，逗号分隔的星期数字1至7',
 schedule_day TINYINT NOT NULL COMMENT '自动策划调度星期，1为周一',
 schedule_time CHAR(5) NOT NULL COMMENT '自动策划调度时间，24小时制HH:mm',
 marketing_max INT NOT NULL COMMENT '单营销账号每周营销内容上限',
 hotspot_ratio INT NOT NULL COMMENT '热点选题占比，整数百分比',
 updated_by VARCHAR(64) NOT NULL COMMENT '最近修改人UM号',
 updated_at DATETIME(3) NOT NULL COMMENT '最近修改时间'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='AI策划业务配置当前版本';

CREATE TABLE IF NOT EXISTS godp_business_planning_config_version (
 id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '历史记录主键',
 config_key VARCHAR(32) NOT NULL COMMENT '配置键，当前固定为operations',
 version INT NOT NULL COMMENT '业务配置版本号',
 planning_days VARCHAR(32) NOT NULL COMMENT '该版本每周策划日',
 schedule_day TINYINT NOT NULL COMMENT '该版本自动策划调度星期',
 schedule_time CHAR(5) NOT NULL COMMENT '该版本自动策划调度时间',
 marketing_max INT NOT NULL COMMENT '该版本单营销账号每周营销内容上限',
 hotspot_ratio INT NOT NULL COMMENT '该版本热点选题占比',
 action VARCHAR(16) NOT NULL COMMENT '版本动作，保存或恢复',
 source_version INT NULL COMMENT '恢复动作所引用的历史版本号',
 created_by VARCHAR(64) NOT NULL COMMENT '创建该版本的操作人UM号',
 created_at DATETIME(3) NOT NULL COMMENT '该版本创建时间',
 UNIQUE KEY uq_business_config_version(config_key, version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='AI策划业务配置历史版本';

CREATE TABLE IF NOT EXISTS godp_planning_config_release (
 command_id VARCHAR(64) NOT NULL PRIMARY KEY COMMENT '两库配置发布命令编号，重试不变',
 version INT NOT NULL COMMENT '页面综合配置版本',
 active_version INT NULL UNIQUE COMMENT '待发布或已发布版本占用，拒绝后释放',
 status VARCHAR(16) NOT NULL COMMENT '发布状态pending completed rejected',
 request_hash CHAR(64) NOT NULL COMMENT '页面提交完整配置指纹',
 config_json LONGTEXT NOT NULL COMMENT '页面综合配置快照，包含业务规则与算法参数',
 business_expected_version INT NOT NULL COMMENT '发布前业务规则版本',
 algorithm_version INT NOT NULL COMMENT '发布前或确认后的算法配置版本',
 created_by VARCHAR(64) NOT NULL COMMENT '配置提交人的可信UM号',
 created_at VARCHAR(40) NOT NULL COMMENT '配置提交时间UTC字符串',
 action VARCHAR(16) NOT NULL COMMENT '保存、恢复或首次迁入',
 source_version INT NULL COMMENT '恢复时引用的综合历史版本',
 last_error VARCHAR(500) NOT NULL DEFAULT '' COMMENT '配置发布失败摘要',
 KEY idx_config_release_state(status,version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='综合配置持久化发布命令与生效历史';
