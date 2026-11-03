package com.stratmatrix.planning.adapter.legacy;

import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.regex.Pattern;

/** 页面旧接口白名单；内部任务、模型管理和系统接口不经页面入口开放。 */
public final class PageRoutes {
    public static final String PREFIX = "/api/plan";
    private static final List<Pattern> ROUTES = Arrays.asList(
        route("GET", "/health"),
        route("GET|PUT", "/config"),
        route("GET", "/config/versions"),
        route("POST", "/config/versions/[0-9]+/restore"),
        route("PUT", "/config/modules/(marketing|strategy)"),
        route("GET", "/config/modules/(marketing|strategy)/versions"),
        route("POST", "/config/modules/(marketing|strategy)/versions/[0-9]+/restore"),
        route("GET|PUT", "/tag-taxonomy"),
        route("GET", "/batches|/items|/planning-accounts|/planning-cycles|/auto-planning/cycles"),
        route("GET", "/batches/[0-9]+"),
        route("POST", "/batches/manual"),
        route("GET", "/items/[0-9]+/(replacement-candidates|adjustments)"),
        route("POST", "/items/[0-9]+/replace-topic"),
        route("GET", "/manual-plans/(account-availability|tasks)"),
        route("POST", "/manual-plans/previews"),
        route("POST", "/manual-plans/previews/[^/]+/submit"),
        route("GET", "/planning-cycles/[^/]+/(items|failures)"),
        route("GET", "/auto-planning/cycles/[^/]+/failures"),
        route("POST", "/query/(manual-tasks|plans|accounts|periods|period-context|failures|export)")
    );

    private PageRoutes() { }
    private static Pattern route(String methods, String path) {
        return Pattern.compile("^(?:" + methods + ") (?:" + path + ")$");
    }

    public static boolean allows(String method, String rawPath) {
        if (!rawPath.startsWith(PREFIX + "/")) return false;
        String path = rawPath.substring(PREFIX.length());
        String lower = path.toLowerCase(Locale.ROOT);
        if (path.contains("..") || path.contains("//") || path.contains("\\") || path.contains(";")
                || lower.matches(".*%(2f|5c|2e|25|00|0d|0a).*")) return false;
        return ROUTES.stream().anyMatch(pattern -> pattern.matcher(method + " " + path).matches());
    }

    public static String pythonPath(String rawPath) {
        return "/api" + rawPath.substring(PREFIX.length());
    }
}
