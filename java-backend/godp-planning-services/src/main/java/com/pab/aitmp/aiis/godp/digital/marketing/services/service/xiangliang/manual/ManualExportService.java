package com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.manual;

import com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.port.ManualPorts;
import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.error.BusinessException;
import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.support.Json;

import static com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.support.Json.*;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.stream.Collectors;
import com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.port.PlanningSpreadsheetWriter;
import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.export.PoiPlanningSpreadsheetWriter;
import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.export.SpreadsheetCells;



/** Builds the same planning report as CSV or an Excel workbook. */
public class ManualExportService {
  static final String[] HEADERS = {
    "账号ID", "账号昵称", "投放日期", "批次号", "策划方式", "选题ID", "选题标题", "选题大纲", "选题二级分类", "内容状态", "最新操作", "操作人",
    "操作时间", "操作说明"
  };
  private final PlanningSpreadsheetWriter writer;
  private final ManualQueryService queries;
  private final ManualItemService items;
  private final ManualPorts.Transition transition;

  public ManualExportService(
      ManualQueryService queries, ManualItemService items, ManualPorts.Transition transition) {
    this(queries,items,transition,new PoiPlanningSpreadsheetWriter());
  }

  public ManualExportService(ManualQueryService queries,ManualItemService items,
      ManualPorts.Transition transition,PlanningSpreadsheetWriter writer) {
    this.writer=Objects.requireNonNull(writer);
    this.queries = queries;
    this.items = items;
    this.transition = transition;
  }

  public byte[] export(Map<String, Object> input) {
    String format = text(input, "format");
    if (!format.isEmpty() && !"csv".equals(format) && !"xlsx".equals(format))
      throw new BusinessException(422, "导出格式无效");
    List<List<String>> rows = reportRows(input);
    return "xlsx".equals(format) ? writer.write(Arrays.asList(HEADERS),rows) : csv(rows);
  }

  List<List<String>> reportRows(Map<String, Object> input) {
    Map<String, Object> query = new LinkedHashMap<>(input);
    query.remove("format");
    query.put("unit", "records");
    query.put("page_size", 200);
    List<Map<String, Object>> frozen = queries.exportRecords(query);
    List<List<String>> output = new ArrayList<>(frozen.size());
    for (int offset = 0; offset < frozen.size(); offset += 200) {
      List<Map<String, Object>> chunk =
          frozen.subList(offset, Math.min(offset + 200, frozen.size()));
      List<Long> oldIds =
          chunk.stream()
              .filter(r -> number(r, "id") < ManualQueryService.JAVA_ID)
              .map(r -> number(r, "id"))
              .collect(Collectors.toList());
      Map<String, Map<String, Object>> operations = new HashMap<>();
      if (queries.businessOnly())
        operations.putAll(
            queries.latestOperations(
                chunk.stream().map(r -> number(r, "id")).collect(Collectors.toList())));
      else if (!oldIds.isEmpty())
        operations.putAll(
            ManualPlanningService.index(transition.latestOperations(oldIds), "item_id"));
      for (Map<String, Object> row : chunk) {
        Map<String, Object> op = operations.get(text(row, "id"));
        if (!queries.businessOnly() && number(row, "id") >= ManualQueryService.JAVA_ID) {
          List<Map<String, Object>> history = items.adjustments(number(row, "id"));
          op = history.isEmpty() ? null : history.get(0);
        }
        String production = text(row, "production_status");
        String state =
            text(row, "topic_id").isEmpty() && text(row, "content_id").isEmpty()
                ? "待定题"
                : Arrays.asList("generated", "published").contains(production)
                    ? "已完成"
                    : "ready".equals(production)
                        ? "生产中"
                        : "failed".equals(production) ? "生产失败" : "待生产";
        List<Object> values =
            Arrays.asList(
                row.get("account_id"),
                row.get("account_name"),
                row.get("publish_date"),
                row.get("batch_code"),
                "manual".equals(row.get("plan_type")) ? "人工策划" : "自动策划",
                row.get("topic_id"),
                row.get("topic_title"),
                row.get("outline"),
                row.get("content_type"),
                state,
                op == null ? "策划结果生成" : op.get("adjustment_source"),
                op == null ? row.get("plan_type") : op.get("created_by"),
                op == null ? row.get("batch_created_at") : op.get("created_at"),
                op == null
                    ? ""
                    : text(op, "old_topic_title")
                        + " → "
                        + text(op, "new_topic_title")
                        + " "
                        + text(op, "reason"));
        output.add(
            values.stream().map(v -> v == null ? "" : v.toString()).collect(Collectors.toList()));
      }
    }
    return output;
  }

  private static byte[] csv(List<List<String>> rows) {
    StringBuilder text = new StringBuilder("\uFEFF");
    text.append(String.join(",", HEADERS)).append("\r\n");
    for (List<String> row : rows)
      text.append(row.stream().map(ManualExportService::csvCell).collect(Collectors.joining(",")))
          .append("\r\n");
    return text.toString().getBytes(StandardCharsets.UTF_8);
  }

  private static String csvCell(String value) {
    String safe = safeText(value);
    return "\"" + safe.replace("\"", "\"\"") + "\"";
  }

  private static String safeText(String value) { return SpreadsheetCells.safe(value); }

}
