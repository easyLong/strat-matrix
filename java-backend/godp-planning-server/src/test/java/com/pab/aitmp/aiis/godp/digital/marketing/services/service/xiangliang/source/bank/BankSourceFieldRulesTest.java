package com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.source.bank;

import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.support.Json;

import static com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.support.Json.*;
import static com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.source.bank.BankSourceMapping.Kind.*;
import static org.junit.jupiter.api.Assertions.*;

import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.error.BusinessException;
import java.time.ZoneId;
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;

class BankSourceFieldRulesTest {
  private BankSourceMapping mapping() {
    return new BankSourceMapping(
        ZoneId.of("Asia/Shanghai"),
        BankSourceFieldRules.builder()
            .alias(ACCOUNT, "account_id", "HOST_ACCOUNT_ID")
            .alias(ACCOUNT, "nickname", "HOST_NICKNAME")
            .alias(ACCOUNT, "eligible", "HOST_ENABLED")
            .alias(ACCOUNT, "interactions", "HOST_INTERACTIONS")
            .alias(INTERACTION, "account_id", "HOST_ACCOUNT_ID")
            .alias(INTERACTION, "content_id", "HOST_CONTENT_ID")
            .code(ACCOUNT, "eligible", "Y", true)
            .code(ACCOUNT, "eligible", "N", false)
            .code(PRODUCTION, "status", 2, "生产中")
            .code(PRODUCTION, "status", 3, "已完成")
            .build());
  }

  private Map<String, Object> account(String id) {
    return map(
        "HOST_ACCOUNT_ID",
        id,
        "HOST_NICKNAME",
        "测试账号",
        "HOST_ENABLED",
        "Y",
        "updated_at",
        "2026-11-03T08:00:00Z");
  }

  @Test
  void siteAliasesAndCodesApplyToNestedDataWithoutChangingSharedContracts() {
    Map<String, Object> account = account("001");
    String before = write(account);
    Map<String, Object> result = mapping().account(account);
    assertEquals("001", result.get("account_id"));
    assertEquals(true, result.get("eligible"));
    assertEquals(before, write(account));
    assertFalse(result.containsKey("HOST_NICKNAME"));
    Map<String, Object> state =
        mapping()
            .production(
                map(
                    "slot_id",
                    "S1",
                    "version",
                    1,
                    "status",
                    2,
                    "updated_at",
                    "2026-11-03T08:00:00Z"));
    assertEquals("生产中", state.get("status"));
    Map<String, Object> unknown =
        map("slot_id", "S1", "version", 1, "status", 999, "updated_at", "2026-11-03T08:00:00Z");
    BusinessException failure =
        assertThrows(BusinessException.class, () -> mapping().production(unknown));
    assertEquals(502, failure.status);
    assertFalse(failure.getMessage().contains("999"));
    account.put("nickname", "其他名称");
    assertThrows(BusinessException.class, () -> mapping().account(account));
  }

  @Test
  void mappingTyposAmbiguousColumnsAndDuplicateCodesFailAtAssembly() {
    assertThrows(
        IllegalArgumentException.class,
        () -> BankSourceFieldRules.builder().alias(ACCOUNT, "nicknme", "n"));
    assertThrows(
        IllegalArgumentException.class,
        () -> BankSourceFieldRules.builder().alias(ACCOUNT, "nickname", "account_id"));
    assertThrows(
        IllegalArgumentException.class,
        () ->
            BankSourceFieldRules.builder()
                .alias(ACCOUNT, "nickname", "shared")
                .alias(ACCOUNT, "platform", "shared"));
    assertThrows(
        IllegalArgumentException.class,
        () ->
            BankSourceFieldRules.builder()
                .code(ACCOUNT, "eligible", 1, true)
                .code(ACCOUNT, "eligible", "1", false));
    BankSourceFieldRules.Builder builder =
        BankSourceFieldRules.builder().alias(ACCOUNT, "nickname", "NICK");
    BankSourceMapping frozen = new BankSourceMapping(ZoneId.of("Asia/Shanghai"), builder.build());
    builder.alias(ACCOUNT, "platform", "PLATFORM");
    Map<String, Object> record = account("001");
    record.put("account_id", "001");
    record.put("NICK", "原始名称");
    record.put("eligible", true);
    record.put("PLATFORM", "不会自动生效");
    Map<String, Object> result = frozen.account(record);
    assertEquals("原始名称", result.get("nickname"));
    assertEquals("", result.get("platform"));
  }

  @Test
  void oneBatchQueryAssemblesWholePagePreservingTotalOrderAndNullCounts() {
    Map<String, Object> first = account("001"), second = account("002");
    first.put("HOST_INTERACTIONS", Collections.singletonList(map("stale", "must be replaced")));
    BankSourceContracts.PageRows page =
        new BankSourceContracts.PageRows(20, Arrays.asList(first, second));
    AtomicInteger queries = new AtomicInteger();
    BankSourceContracts.PageRows joined =
        BankSourceInteractions.attach(
            page,
            ids -> {
              queries.incrementAndGet();
              assertEquals(Arrays.asList("001", "002"), ids);
              assertThrows(UnsupportedOperationException.class, () -> ids.add("003"));
              return Collections.singletonList(
                  map(
                      "HOST_ACCOUNT_ID",
                      "002",
                      "HOST_CONTENT_ID",
                      "C1",
                      "published_at",
                      "2026-11-03T08:00:00Z",
                      "likes",
                      null));
            },
            mapping());
    assertEquals(1, queries.get());
    assertEquals(20, joined.total);
    assertEquals("001", mapping().account(joined.items.get(0)).get("account_id"));
    assertTrue(rows(mapping().account(joined.items.get(0)).get("interactions")).isEmpty());
    Map<String, Object> result = mapping().account(joined.items.get(1));
    assertEquals("C1", rows(result.get("interactions")).get(0).get("content_id"));
    assertNull(rows(result.get("interactions")).get(0).get("likes"));
    assertTrue(first.containsKey("HOST_INTERACTIONS"));
    assertFalse(second.containsKey("interactions"));
    BankSourceInteractions.attach(
        new BankSourceContracts.PageRows(0, Collections.emptyList()),
        ids -> {
          fail("empty page must not query interactions");
          return null;
        },
        mapping());
  }

  @Test
  void interactionBatchRejectsCrossAccountRowsDuplicatesAndMissingResults() {
    BankSourceContracts.PageRows page =
        new BankSourceContracts.PageRows(1, Collections.singletonList(account("001")));
    Map<String, Object> wrong = map("HOST_ACCOUNT_ID", "999", "HOST_CONTENT_ID", "C1");
    assertThrows(
        BusinessException.class,
        () ->
            BankSourceInteractions.attach(
                page, ids -> Collections.singletonList(wrong), mapping()));
    Map<String, Object> duplicate = map("HOST_ACCOUNT_ID", "001", "HOST_CONTENT_ID", "C1");
    assertThrows(
        BusinessException.class,
        () ->
            BankSourceInteractions.attach(
                page, ids -> Arrays.asList(duplicate, duplicate), mapping()));
    assertThrows(
        BusinessException.class, () -> BankSourceInteractions.attach(page, ids -> null, mapping()));
  }
}
