package com.stratmatrix.planning.query;

import static com.stratmatrix.planning.manual.Json.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import com.stratmatrix.planning.manual.*;
import java.util.*;
import org.junit.jupiter.api.Test;

class CurrentAccountFactsTest {
  @Test
  void readsOnlyPageAccountsAndPreservesSnapshotLifecycleForSqlFilters() {
    PlanningQueryMapper mapper = mock(PlanningQueryMapper.class);
    ManualPorts.AccountFacts source = mock(ManualPorts.AccountFacts.class);
    when(mapper.accountGroups(anyMap()))
        .thenReturn(Collections.singletonList(map("account_id", "A", "latest_time", 1L)));
    when(mapper.accountSnapshots(anyMap()))
        .thenReturn(
            Collections.singletonList(
                map(
                    "account_id",
                    "A",
                    "payload",
                    write(
                        map(
                            "account_snapshot",
                            map(
                                "account_id",
                                "A",
                                "account_name",
                                "旧昵称",
                                "lifecycle_stage",
                                "冷启动期"))))));
    when(source.sourceAccounts(Collections.singletonList("A")))
        .thenReturn(
            map(
                "accounts",
                Collections.singletonList(
                    map(
                        "account_id",
                        "A",
                        "account_name",
                        "当前昵称",
                        "status",
                        "启用",
                        "gender",
                        "女",
                        "um_no",
                        "TESTUM1",
                        "lifecycle_stage",
                        "稳定经营期"))));
    Map<String, Object> page =
        new SqlPlanningReadQueries(mapper, null, null, source)
            .accounts(map("page", 1, "page_size", 20, "filters", map()));
    Map<String, Object> profile = object(rows(page.get("items")).get(0).get("profile"));
    assertEquals("当前昵称", profile.get("account_name"));
    assertEquals("启用", profile.get("status"));
    assertEquals("女", profile.get("gender"));
    assertEquals("冷启动期", profile.get("lifecycle_stage"));
    verify(source).sourceAccounts(Collections.singletonList("A"));
  }
}
