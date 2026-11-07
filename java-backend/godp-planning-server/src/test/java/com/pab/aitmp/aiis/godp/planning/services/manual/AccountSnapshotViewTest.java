package com.pab.aitmp.aiis.godp.planning.services.manual;

import com.pab.aitmp.aiis.godp.planning.entity.support.Json;

import static com.pab.aitmp.aiis.godp.planning.entity.support.Json.*;
import static org.junit.jupiter.api.Assertions.*;

import java.util.*;
import org.junit.jupiter.api.Test;

class AccountSnapshotViewTest {
  @Test
  void readsAlgorithmSnapshotWithoutMutatingFrozenFacts() {
    Map<String, Object> snapshot =
        map(
            "account_id",
            "A",
            "followers_count",
            0,
            "lifecycle_stage",
            "冷启动期",
            "source_payload",
            map(
                "um_no",
                "TESTUM1",
                "organization",
                "测试分行/测试二级分行",
                "platform",
                "小红书",
                "account_type",
                "认证",
                "gender",
                "女",
                "interests",
                Arrays.asList("储蓄"),
                "account_status",
                false));
    String before = write(snapshot);
    Map<String, Object> view = AccountSnapshotView.from(snapshot);
    assertEquals("TESTUM1", view.get("um_no"));
    assertEquals("认证", view.get("account_type"));
    assertEquals("测试分行/测试二级分行", view.get("organization"));
    assertEquals("小红书", view.get("platform"));
    assertEquals("停用", view.get("status"));
    assertEquals(0, view.get("followers"));
    assertEquals(before, write(snapshot));
  }

  @Test
  void preservesFlatPageFactsAndUsesNestedValuesForEmptyAliases() {
    Map<String, Object> snapshot =
        map(
            "um_no",
            "",
            "followers",
            10,
            "status",
            "启用",
            "source_payload",
            map("um_no", "TESTUM2", "follower_count", 20));
    Map<String, Object> view = AccountSnapshotView.from(snapshot);
    assertEquals("TESTUM2", view.get("um_no"));
    assertEquals(10, view.get("followers"));
    assertEquals("启用", view.get("status"));
  }
}
