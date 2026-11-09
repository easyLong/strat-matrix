package com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.source.bank;

import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.support.Json;

import static com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.source.bank.BankSourceValues.*;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.*;
import java.util.*;

/**
 * Whitelisted wire objects. SQL uses AS aliases; bank-specific code conversion stays in this
 * boundary.
 */
public class BankSourceMapping {
  public enum Kind {
    ACCOUNT,
    INTERACTION,
    TOPIC,
    MARKETING,
    PLACEMENT,
    PRODUCTION,
    MARKETING_STATUS,
    APPROVED
  }

  private final ZoneId storageZone;
  private final BankSourceFieldRules rules;
  private static final ObjectMapper JSON = new ObjectMapper();

  public BankSourceMapping() {
    this(BEIJING);
  }

  public BankSourceMapping(ZoneId storageZone) {
    this(storageZone, BankSourceFieldRules.none());
  }

  public BankSourceMapping(ZoneId storageZone, BankSourceFieldRules rules) {
    this.storageZone = Objects.requireNonNull(storageZone);
    this.rules = Objects.requireNonNull(rules);
  }

  private static final class Field {
    final String name, alias;
    final char type;
    final boolean required;

    Field(String name, String alias, char type, boolean required) {
      this.name = name;
      this.alias = alias;
      this.type = type;
      this.required = required;
    }
  }

  private static Field f(String name, String alias, char type, boolean required) {
    return new Field(name, alias, type, required);
  }
  // i: business ID; s: text; t: timestamp; d: date; b: boolean; n: integer; v: version;
  // h: heat; l: text list; x: interaction list; a: account type.
  private static final Field[] ACCOUNT = {
    f("account_id", "账号ID", 'i', true), f("nickname", "账号昵称", 's', true),
    f("owner_um", "属主UM号", 's', false), f("organization", "属主组织", 's', false),
    f("platform", "平台", 's', false), f("account_type", "账号类型", 'a', false),
    f("eligible", "可参与策划", 'b', true), f("followers", "粉丝量", 'n', false),
    f("updated_at", "账号信息更新时间", 't', true), f("persona", "账号人设", 's', false),
    f("gender", "性别", 's', false), f("interests", "兴趣爱好", 'l', false),
    f("expression_style", "表达风格", 's', false), f("interactions", "近三个月内容互动明细", 'x', false)
  };
  private static final Field[] INTERACTION = {
    f("content_id", "内容ID", 'i', true), f("account_id", "账号ID", 'i', true),
    f("published_at", "发布时间", 't', true), f("title", "内容标题", 's', false),
    f("likes", "点赞数", 'n', false), f("favorites", "收藏数", 'n', false),
    f("comments", "评论数", 'n', false), f("updated_at", "互动数据更新时间", 't', false)
  };
  private static final Field[] TOPIC = {
    f("topic_id", "选题ID", 'i', true), f("source", "选题来源", 's', true),
    f("topic_type", "选题类型", 's', true), f("title", "选题标题", 's', false),
    f("outline", "选题大纲", 's', false), f("content_type", "选题二级分类", 's', false),
    f("heat", "热度", 'h', false), f("available", "可用状态", 'b', true),
    f("valid_from", "有效开始时间", 't', false), f("valid_to", "有效结束时间", 't', false),
    f("updated_at", "选题更新时间", 't', true), f("related_product", "关联产品", 's', false),
    f("related_activity", "关联活动", 's', false), f("related_hotspot", "关联属地热点", 's', false),
    f("related_product_id", "关联产品ID", 's', false),
    f("related_activity_id", "关联活动ID", 's', false),
    f("activity_organization", "活动所属组织", 's', false)
  };
  private static final Field[] MARKETING = {
    f("content_id", "内容ID", 'i', true), f("account_id", "绑定账号ID", 'i', true),
    f("title", "内容标题", 's', true), f("body", "内容正文", 's', true),
    f("related_product", "关联产品", 's', false), f("related_activity", "关联活动", 's', false),
    f("approved_at", "审核通过时间", 't', true)
  };
  private static final Field[] PLACEMENT = {
    f("placement_id", "投放记录ID", 'i', true), f("account_id", "账号ID", 'i', true),
    f("content_id", "内容ID", 'i', true), f("publish_date", "投放日期", 'd', true)
  };
  private static final Field[] PRODUCTION = {
    f("slot_id", "slot_id", 'i', true), f("version", "version", 'v', true),
    f("content_id", "内容ID", 'i', false), f("status", "内容状态", 's', true),
    f("updated_at", "状态更新时间", 't', true), f("production_task_id", "生产任务ID", 'i', false),
    f("error", "失败原因", 's', false)
  };
  private static final Field[] MARKETING_STATUS = {
    f("task_code", "task_code", 'i', true), f("status", "内容状态", 's', true),
    f("completed_count", "完成数", 'n', true), f("failed_count", "失败数", 'n', true),
    f("account_count", "已分配账号数", 'n', true), f("updated_at", "状态更新时间", 't', true)
  };
  private static final Field[] APPROVED = {
    f("task_code", "task_code", 'i', true), f("content_id", "内容ID", 'i', true),
    f("account_id", "绑定账号ID", 'i', true), f("title", "内容标题", 's', true),
    f("body", "内容正文", 's', true), f("content_type", "选题二级分类", 's', true),
    f("approved_at", "审核通过时间", 't', true)
  };

  public Map<String, Object> account(Map<String, Object> row) {
    Map<String, Object> out = normalize(Kind.ACCOUNT, row);
    if (out.get("account_type") != null) member(out, "account_type", "认证", "非认证");
    if ("M".equals(out.get("gender"))) out.put("gender", "男");
    if ("F".equals(out.get("gender"))) out.put("gender", "女");
    for (Map<String, Object> interaction :
        com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.support.Json.rows(out.get("interactions")))
      if (!out.get("account_id").equals(interaction.get("account_id")))
        throw invalid(502, "互动明细账号与所属账号不一致");
    return out;
  }

  public Map<String, Object> topic(Map<String, Object> row) {
    Map<String, Object> out = normalize(Kind.TOPIC, row);
    member(out, "source", "普通", "热点");
    member(out, "topic_type", "营销", "非营销");
    if ("非营销".equals(out.get("topic_type")) && text(out.get("title"), "选题标题", false, 0, 502).trim().isEmpty())
      throw invalid(502, "非营销选题必须提供选题标题");
    if (out.get("valid_from") != null
        && out.get("valid_to") != null
        && instant(out, "valid_from").isAfter(instant(out, "valid_to")))
      throw invalid(502, "选题有效期倒置");
    return out;
  }

  public Map<String, Object> marketing(Map<String, Object> row) {
    return normalize(Kind.MARKETING, row);
  }

  public Map<String, Object> placement(Map<String, Object> row) {
    return normalize(Kind.PLACEMENT, row);
  }

  public Map<String, Object> production(Map<String, Object> row) {
    Map<String, Object> out = normalize(Kind.PRODUCTION, row);
    member(out, "status", "待生产", "生产中", "已完成", "生产失败");
    if ("已完成".equals(out.get("status")) && out.get("content_id") == null)
      throw invalid(502, "已完成内容缺少内容ID");
    return out;
  }

  public Map<String, Object> marketingStatus(Map<String, Object> row) {
    Map<String, Object> out = normalize(Kind.MARKETING_STATUS, row);
    member(out, "status", "待分配", "待生产", "生产中", "已完成", "生产失败");
    if ("已完成".equals(out.get("status")) && ((Number) out.get("failed_count")).longValue() != 0)
      throw invalid(502, "营销已完成状态仍含失败数");
    return out;
  }

  public Map<String, Object> approved(Map<String, Object> row) {
    return normalize(Kind.APPROVED, row);
  }

  private static Field[] schema(Kind kind) {
    switch (Objects.requireNonNull(kind)) {
      case ACCOUNT:
        return ACCOUNT;
      case INTERACTION:
        return INTERACTION;
      case TOPIC:
        return TOPIC;
      case MARKETING:
        return MARKETING;
      case PLACEMENT:
        return PLACEMENT;
      case PRODUCTION:
        return PRODUCTION;
      case MARKETING_STATUS:
        return MARKETING_STATUS;
      case APPROVED:
        return APPROVED;
      default:
        throw new IllegalArgumentException("未知资料对象");
    }
  }

  static Set<String> fieldNames(Kind kind) {
    Set<String> names = new LinkedHashSet<>();
    for (Field field : schema(kind)) names.add(field.name);
    return names;
  }

  static String canonicalField(Kind kind, String column) {
    for (Field field : schema(kind))
      if (field.name.equals(column) || field.alias.equals(column)) return field.name;
    return null;
  }

  String recordId(Kind kind, String field, Map<String, Object> row) {
    for (Field definition : schema(kind))
      if (definition.name.equals(field))
        return id(rules.read(kind, row, field, definition.alias), field, 502);
    throw new IllegalArgumentException("未知资料标识");
  }

  Map<String, Object> withInteractions(
      Map<String, Object> row, List<Map<String, Object>> interactions) {
    Map<String, Object> copy = new LinkedHashMap<>(row);
    copy.remove("interactions");
    copy.remove("近三个月内容互动明细");
    rules.removeAlias(Kind.ACCOUNT, "interactions", copy);
    copy.put("interactions", interactions);
    return copy;
  }

  private Map<String, Object> normalize(Kind kind, Map<String, Object> row) {
    Map<String, Object> out = new LinkedHashMap<>();
    for (Field field : schema(kind)) {
      Object raw = rules.read(kind, row, field.name, field.alias);
      if (raw == null) {
        if (field.required) throw invalid(502, field.alias + "缺失");
        out.put(
            field.name,
            field.type == 's'
                ? ""
                : field.type == 'l' || field.type == 'x' ? new ArrayList<>() : null);
        continue;
      }
      Object converted;
      switch (field.type) {
        case 'i':
          converted = text(raw, field.alias, true, "slot_id".equals(field.name) ? 128 : 64, 502);
          if (!converted.equals(((String) converted).trim()))
            throw invalid(502, field.alias + "不能含首尾空格");
          break;
        case 's':
          converted =
              text(raw, field.alias, field.required, "error".equals(field.name) ? 500 : 0, 502);
          break;
        case 'a':
          converted =
              raw instanceof Boolean
                  ? ((Boolean) raw ? "认证" : "非认证")
                  : text(raw, field.alias, true, 0, 502);
          break;
        case 'b':
          converted = bool(raw, field.alias, 502);
          break;
        case 'n':
          converted =
              integer(
                  raw,
                  field.alias,
                  0,
                  field.name.endsWith("_count") ? Integer.MAX_VALUE : Long.MAX_VALUE,
                  502);
          break;
        case 'v':
          converted = integer(raw, field.alias, 1, Integer.MAX_VALUE, 502);
          break;
        case 't':
          converted = iso(time(raw, field.alias, storageZone, 502));
          break;
        case 'd':
          converted = date(raw, field.alias, 502).toString();
          break;
        case 'h':
          try {
            converted = Double.valueOf(raw.toString());
          } catch (RuntimeException error) {
            throw invalid(502, field.alias);
          }
          if (!Double.isFinite((Double) converted) || (Double) converted < 0)
            throw invalid(502, field.alias);
          break;
        case 'l':
          List<String> strings = new ArrayList<>();
          for (Object item : list(raw, field.alias))
            strings.add(text(item, field.alias, true, 0, 502));
          converted = strings;
          break;
        case 'x':
          List<Map<String, Object>> interactions = new ArrayList<>();
          for (Object item : list(raw, field.alias)) {
            if (!(item instanceof Map)) throw invalid(502, field.alias);
            @SuppressWarnings("unchecked")
            Map<String, Object> record = (Map<String, Object>) item;
            interactions.add(normalize(Kind.INTERACTION, record));
          }
          converted = interactions;
          break;
        default:
          throw new IllegalStateException("unknown source field type");
      }
      out.put(field.name, converted);
    }
    return out;
  }

  private static List<?> list(Object raw, String field) {
    try {
      Object values = raw instanceof String ? JSON.readValue((String) raw, Object.class) : raw;
      if (!(values instanceof List)) throw invalid(502, field);
      return (List<?>) values;
    } catch (Exception error) {
      throw invalid(502, field + "应为数组或JSON数组");
    }
  }

  private static void member(Map<String, Object> row, String field, String... options) {
    if (!Arrays.asList(options).contains(row.get(field))) throw invalid(502, field + "含未映射编码");
  }

  static Instant instant(Map<String, Object> row, String name) {
    return time(row.get(name), name, BEIJING, 502);
  }
}
