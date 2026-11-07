package com.pab.aitmp.aiis.godp.planning.services.manual;

import com.pab.aitmp.aiis.godp.planning.entity.support.Json;

import static com.pab.aitmp.aiis.godp.planning.entity.support.Json.*;

import java.util.*;

/** Maps immutable algorithm snapshots and legacy flat account facts into one page contract. */
public final class AccountSnapshotView {
  private AccountSnapshotView() {}

  public static Map<String, Object> from(Map<String, Object> snapshot) {
    Map<String, Object> source = object(snapshot.get("source_payload"));
    Map<String, Object> view = new LinkedHashMap<>(source);
    view.putAll(snapshot);
    alias(
        view,
        "account_name",
        snapshot.get("account_name"),
        source.get("account_name"),
        source.get("nickname"));
    alias(view, "um_no", snapshot.get("um_no"), source.get("um_no"), source.get("owner_um"));
    for (String key :
        Arrays.asList(
            "organization", "platform", "account_type", "gender", "interests", "expression_style"))
      alias(view, key, snapshot.get(key), source.get(key));
    alias(
        view,
        "persona",
        snapshot.get("persona"),
        source.get("persona"),
        source.get("account_persona"));
    alias(
        view,
        "followers",
        snapshot.get("followers"),
        snapshot.get("followers_count"),
        source.get("followers"),
        source.get("follower_count"));
    alias(
        view,
        "certified",
        snapshot.get("certified"),
        source.get("certified"),
        source.get("certification_status"));
    if (blank(view.get("account_type")) && view.get("certified") instanceof Boolean)
      view.put("account_type", Boolean.TRUE.equals(view.get("certified")) ? "认证" : "非认证");
    Object eligible =
        source.containsKey("account_status")
            ? source.get("account_status")
            : source.get("eligible");
    if (blank(view.get("status")) && eligible instanceof Boolean)
      view.put("status", Boolean.TRUE.equals(eligible) ? "启用" : "停用");
    return view;
  }

  private static boolean blank(Object value) {
    return value == null || value instanceof String && ((String) value).trim().isEmpty();
  }

  private static void alias(Map<String, Object> view, String key, Object... values) {
    for (Object value : values)
      if (!blank(value)) {
        view.put(key, value);
        return;
      }
  }
}
