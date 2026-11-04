package com.stratmatrix.planning.source.bank;

import static com.stratmatrix.planning.source.bank.BankSourceValues.invalid;

import java.util.*;
import java.util.function.Function;

/** Assemble one account page with a single batch query; no extra public source capability. */
public final class BankSourceInteractions {
  private BankSourceInteractions() {}

  public static BankSourceContracts.PageRows attach(
      BankSourceContracts.PageRows page,
      Function<List<String>, List<Map<String, Object>>> batchQuery,
      BankSourceMapping mapping) {
    Objects.requireNonNull(page);
    Objects.requireNonNull(batchQuery);
    Objects.requireNonNull(mapping);
    if (page.items.isEmpty()) return page;
    if (page.items.size() > 500) throw invalid(502, "互动批量查询账号数超过单页上限");
    Map<String, List<Map<String, Object>>> groups = new LinkedHashMap<>();
    for (Map<String, Object> account : page.items) {
      String id = mapping.recordId(BankSourceMapping.Kind.ACCOUNT, "account_id", account);
      if (groups.put(id, new ArrayList<>()) != null) throw invalid(502, "账号分页存在重复ID");
    }
    List<Map<String, Object>> loaded =
        batchQuery.apply(Collections.unmodifiableList(new ArrayList<>(groups.keySet())));
    if (loaded == null) throw invalid(502, "互动批量查询未返回列表");
    Set<List<String>> seen = new HashSet<>();
    for (Map<String, Object> interaction : loaded) {
      String account =
          mapping.recordId(BankSourceMapping.Kind.INTERACTION, "account_id", interaction);
      String content =
          mapping.recordId(BankSourceMapping.Kind.INTERACTION, "content_id", interaction);
      if (!groups.containsKey(account)) throw invalid(502, "互动明细超出本页账号范围");
      if (!seen.add(Arrays.asList(account, content))) throw invalid(502, "互动明细存在重复内容");
      groups.get(account).add(new LinkedHashMap<>(interaction));
    }
    List<Map<String, Object>> items = new ArrayList<>();
    for (Map<String, Object> account : page.items)
      items.add(
          mapping.withInteractions(
              account,
              groups.get(mapping.recordId(BankSourceMapping.Kind.ACCOUNT, "account_id", account))));
    return new BankSourceContracts.PageRows(page.total, items);
  }
}
