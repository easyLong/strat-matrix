package com.stratmatrix.planning.source.bank;

import static com.stratmatrix.planning.manual.Json.*;
import static org.junit.jupiter.api.Assertions.*;

import com.stratmatrix.planning.manual.BusinessException;
import java.time.*;
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

class BankSourceFactsTest {
  static Map<String, Object> account() {
    return map(
        "账号ID",
        "A1",
        "账号昵称",
        "契约测试账号",
        "属主UM号",
        "UM001",
        "属主组织",
        "测试二级分行",
        "平台",
        "小红书",
        "账号类型",
        true,
        "可参与策划",
        1,
        "粉丝量",
        "123",
        "账号信息更新时间",
        java.sql.Timestamp.valueOf("2026-11-03 16:00:00"),
        "账号人设",
        "车圈达人",
        "性别",
        "M",
        "兴趣爱好",
        "[\"汽车\",\"理财\"]",
        "表达风格",
        "简明",
        "近三个月内容互动明细",
        Collections.singletonList(
            map(
                "内容ID",
                "C1",
                "账号ID",
                "A1",
                "发布时间",
                "2026-11-03 15:00:00",
                "内容标题",
                "互动内容",
                "收藏数",
                "3",
                "评论数",
                7)),
        "private_column",
        "not forwarded");
  }

  static Map<String, Object> topic() {
    return map(
        "选题ID",
        "T1",
        "选题来源",
        "普通",
        "选题类型",
        "非营销",
        "选题标题",
        "选题标题",
        "选题大纲",
        "选题大纲",
        "选题二级分类",
        "金融科普",
        "热度",
        "2.5",
        "可用状态",
        true,
        "有效开始时间",
        "2026-11-01 00:00:00",
        "有效结束时间",
        "2026-12-31 23:59:59",
        "选题更新时间",
        "2026-11-03T08:00:00Z");
  }

  static Map<String, Object> marketing() {
    return map(
        "内容ID",
        "M1",
        "绑定账号ID",
        "A1",
        "内容标题",
        "营销标题",
        "内容正文",
        "营销正文",
        "审核通过时间",
        "2026-11-03 09:00:00");
  }

  static class Reader implements BankSourceQueries {
    final AtomicInteger calls = new AtomicInteger();
    List<Map<String, Object>> accountRows = new ArrayList<>(Collections.singletonList(account()));
    List<Map<String, Object>> topicRows = new ArrayList<>(Collections.singletonList(topic()));
    Long total;

    public BankSourceContracts.PageRows accounts(BankSourceContracts.Accounts q) {
      calls.incrementAndGet();
      return new BankSourceContracts.PageRows(
          total == null ? accountRows.size() : total, accountRows);
    }

    public BankSourceContracts.PageRows topics(BankSourceContracts.Topics q) {
      return new BankSourceContracts.PageRows(topicRows.size(), topicRows);
    }

    public BankSourceContracts.PageRows marketingContents(BankSourceContracts.Marketing q) {
      return new BankSourceContracts.PageRows(1, Collections.singletonList(marketing()));
    }

    public List<Map<String, Object>> effectiveMarketing(BankSourceContracts.Placement q) {
      return Collections.singletonList(
          map(
              "投放记录ID",
              "P1",
              "账号ID",
              "A1",
              "内容ID",
              "M1",
              "投放日期",
              java.sql.Date.valueOf("2026-11-04")));
    }

    public List<Map<String, Object>> productionStatus(BankSourceContracts.Production q) {
      return Collections.singletonList(
          map(
              "slot_id",
              "JSLOT-1-A1",
              "version",
              2,
              "内容ID",
              "C1",
              "内容状态",
              "已完成",
              "状态更新时间",
              "2026-11-03 16:00:00",
              "生产任务ID",
              "PROD1"));
    }

    public List<Map<String, Object>> marketingStatus(BankSourceContracts.MarketingStatus q) {
      return Collections.singletonList(
          map(
              "task_code",
              "MKT1",
              "内容状态",
              "已完成",
              "完成数",
              "1",
              "失败数",
              0,
              "已分配账号数",
              1,
              "状态更新时间",
              "2026-11-03 16:00:00"));
    }

    public List<Map<String, Object>> approvedDemandContents(BankSourceContracts.ApprovedDemand q) {
      return Collections.singletonList(approved("M1", "2026-11-03T01:00:00Z"));
    }
  }

  static Map<String, Object> approved(String id, String at) {
    Map<String, Object> r = marketing();
    r.put("内容ID", id);
    r.put("task_code", "MKT1");
    r.put("选题二级分类", "产品营销");
    r.put("审核通过时间", at);
    return r;
  }

  @Test
  void allSevenCapabilitiesMatchSharedPythonWireFixture() throws Exception {
    BankSourceFacts f = new BankSourceFacts(new Reader());
    Map<String, Object> results =
        map(
            "accounts",
            f.accounts(map()),
            "topics",
            f.topics(map()),
            "marketing-contents",
            f.marketingContents(map("账号ID", "A1")),
            "effective-marketing",
            f.effectiveMarketing(map("账号ID", "A1", "投放日期", "2026-11-04")),
            "production-status",
            f.productionStatus(map("slot_ids", Collections.singletonList("JSLOT-1-A1"))),
            "marketing-status",
            f.marketingStatus(map("task_codes", Collections.singletonList("MKT1"))),
            "marketing-allocations",
            f.approvedDemandContents(map("task_code", "MKT1")));
    com.fasterxml.jackson.databind.ObjectMapper json =
        new com.fasterxml.jackson.databind.ObjectMapper();
    try (java.io.InputStream input =
        getClass().getResourceAsStream("/bank-source/contract-sample.json")) {
      assertEquals(json.readTree(input), json.readTree(write(results)));
    }
  }

  @Test
  void inputValidationRunsBeforeReaderAndDoesNotMutateArguments() {
    Reader reader = new Reader();
    BankSourceFacts f = new BankSourceFacts(reader);
    for (Map<String, Object> q :
        Arrays.asList(
            map("page_no", 0),
            map("page_size", 501),
            map("page_no", 1.5),
            map("page_no", "1"),
            map("updated_from", "2026-11-03T08:00:00Z", "updated_to", "2026-11-03T08:00:00Z"),
            map("account_ids", "A1"),
            map("page_size", 1, "每页条数", 2),
            map("wrong_filter", true)))
      assertEquals(422, assertThrows(BusinessException.class, () -> f.accounts(q)).status);
    assertEquals(0, reader.calls.get());
    assertEquals(0, number(f.accounts(map("account_ids", Collections.emptyList())), "total"));
    assertEquals(0, reader.calls.get());
    Map<String, Object> q = map("账号ID列表", Arrays.asList("A1", "A1"));
    String original = write(q);
    assertEquals(1, number(f.accounts(q), "total"));
    assertEquals(original, write(q));
    assertEquals(Collections.singletonList("A1"), new BankSourceContracts.Accounts(q).accountIds);
  }

  @Test
  void pageCountsEligibilityIdentityAndScopeAreCheckedWithoutFilteringRowsAfterPagination() {
    Reader reader = new Reader();
    BankSourceFacts f = new BankSourceFacts(reader);
    reader.total = 10L;
    assertEquals(502, assertThrows(BusinessException.class, () -> f.accounts(map())).status);
    reader.total = 1L;
    reader.accountRows.get(0).put("可参与策划", false);
    assertThrows(BusinessException.class, () -> f.accounts(map()));
    reader.accountRows = new ArrayList<>(Collections.singletonList(account()));
    assertThrows(
        BusinessException.class,
        () -> f.accounts(map("account_ids", Collections.singletonList("OTHER"))));
    reader.accountRows.add(account());
    reader.total = 2L;
    assertThrows(BusinessException.class, () -> f.accounts(map()));
    reader.accountRows = null;
    assertThrows(BusinessException.class, () -> f.accounts(map()));
  }

  @Test
  void updateWindowIsHalfOpenAndSourceTimezoneIsExplicit() {
    Reader reader = new Reader();
    BankSourceFacts f = new BankSourceFacts(reader);
    assertEquals(1, number(f.accounts(map("updated_from", "2026-11-03T08:00:00Z")), "total"));
    assertThrows(
        BusinessException.class, () -> f.accounts(map("updated_to", "2026-11-03T08:00:00Z")));
    assertEquals(
        "2026-11-04T00:00:00+08:00",
        new BankSourceMapping(ZoneId.of("UTC")).account(account()).get("updated_at"));
    reader.accountRows.get(0).put("账号信息更新时间", "2026-11-03");
    assertThrows(BusinessException.class, () -> f.accounts(map()));
  }

  @Test
  void noUnknownDataIsInventedAndPrivateColumnsAreNotForwarded() {
    Map<String, Object> input = account();
    String original = write(input);
    Map<String, Object> mapped = new BankSourceMapping().account(input);
    assertFalse(mapped.containsKey("private_column"));
    assertEquals(original, write(input));
    Map<String, Object> interaction = rows(mapped.get("interactions")).get(0);
    assertNull(interaction.get("likes"));
    assertFalse(interaction.containsKey("shares"));
    input.remove("粉丝量");
    assertNull(new BankSourceMapping().account(input).get("followers"));
    input.put("account_id", "A2");
    assertThrows(BusinessException.class, () -> new BankSourceMapping().account(input));
    Map<String, Object> wrong = account();
    wrong.put(
        "近三个月内容互动明细",
        Collections.singletonList(
            map(
                "content_id",
                "C2",
                "account_id",
                "OTHER",
                "published_at",
                "2026-11-03T08:00:00Z")));
    assertThrows(BusinessException.class, () -> new BankSourceMapping().account(wrong));
  }

  @Test
  void marketingTopicsUseActivityOrProductFactsWithoutTitleOrOutline() {
    BankSourceMapping mapper = new BankSourceMapping();
    Map<String, Object> row = topic();
    row.remove("选题标题");
    row.remove("选题大纲");
    assertEquals(502, assertThrows(BusinessException.class, () -> mapper.topic(row)).status);
    row.put("选题类型", "营销");
    row.put("关联活动ID", "ACT-001");
    row.put("关联活动", "测试活动");
    row.put("活动所属组织", "测试二级分行");
    row.put("关联产品ID", "PRODUCT-001");
    Map<String, Object> result = mapper.topic(row);
    assertEquals("", result.get("title"));
    assertEquals("", result.get("outline"));
    assertEquals("ACT-001", result.get("related_activity_id"));
    assertEquals("测试二级分行", result.get("activity_organization"));
    assertEquals("PRODUCT-001", result.get("related_product_id"));
  }

  @Test
  void topicFiltersAndValidityAreChecked() {
    BankSourceFacts f = new BankSourceFacts(new Reader());
    for (Map<String, Object> q :
        Arrays.asList(
            map("选题来源", "热点"), map("选题类型", "营销"), map("有效时点", "2027-01-01T00:00:00+08:00")))
      assertThrows(BusinessException.class, () -> f.topics(q));
    assertEquals(
        1,
        number(
            f.topics(map("选题来源", "普通", "仅可用选题", true, "有效时点", "2026-11-01T00:00:00+08:00")),
            "total"));
    assertEquals(
        422, assertThrows(BusinessException.class, () -> f.topics(map("source", "auto"))).status);
    assertThrows(BusinessException.class, () -> f.topics(map("available_only", "true")));
    Reader reader = new Reader();
    reader.topicRows.get(0).put("有效结束时间", "2026-10-01 00:00:00");
    assertThrows(BusinessException.class, () -> new BankSourceFacts(reader).topics(map()));
  }

  @ParameterizedTest
  @ValueSource(strings = {"生成中", "SUCCESS", "未知"})
  void unknownContentStatusNeedsAnExplicitSiteMapping(String status) {
    Map<String, Object> row =
        map("slot_id", "S1", "version", 1, "status", status, "updated_at", "2026-11-03T08:00:00Z");
    assertThrows(BusinessException.class, () -> new BankSourceMapping().production(row));
  }

  @Test
  void productionAssociationsDuplicatesAndCompletedContentAreValidated() {
    Reader reader = new Reader();
    BankSourceFacts f = new BankSourceFacts(reader);
    assertThrows(
        BusinessException.class,
        () -> f.productionStatus(map("slot_ids", Collections.singletonList("OTHER"))));
    assertThrows(
        BusinessException.class,
        () -> f.marketingStatus(map("task_codes", Collections.singletonList("OTHER"))));
    assertThrows(
        BusinessException.class, () -> f.approvedDemandContents(map("task_code", "OTHER")));
    assertThrows(
        BusinessException.class,
        () -> f.effectiveMarketing(map("account_id", "A1", "publish_date", "2026-11-05")));
    assertThrows(BusinessException.class, () -> f.marketingContents(map("account_id", "OTHER")));
    assertThrows(
        BusinessException.class,
        () ->
            new BankSourceMapping()
                .production(
                    map(
                        "slot_id",
                        "S1",
                        "version",
                        1,
                        "status",
                        "已完成",
                        "updated_at",
                        "2026-11-03T08:00:00Z")));
    assertThrows(
        BusinessException.class,
        () -> f.productionStatus(map("slot_ids", Collections.emptyList())));
  }

  @Test
  void approvalsSortByInstantBeforeContentIdAndUnimplementedReadersFailExplicitly() {
    BankSourceFacts f =
        new BankSourceFacts(
            new Reader() {
              public List<Map<String, Object>> approvedDemandContents(
                  BankSourceContracts.ApprovedDemand q) {
                return Arrays.asList(
                    approved("M2", "2026-11-03T09:00:00+08:00"),
                    approved("M1", "2026-11-03T01:00:00Z"));
              }
            });
    assertEquals(
        "M1", rows(f.approvedDemandContents(map("task_code", "MKT1"))).get(0).get("content_id"));
    BankSourceFacts empty = new BankSourceFacts(new BankSourceQueries() {});
    assertEquals(503, assertThrows(BusinessException.class, () -> empty.accounts(map())).status);
    assertEquals(
        503,
        assertThrows(
                BusinessException.class,
                () -> empty.approvedDemandContents(map("task_code", "MKT1")))
            .status);
  }
}
