package com.stratmatrix.planning.adapter.legacy;

import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.util.StreamUtils;
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

/** 真实本地HTTP上游，验证转发字节、状态、权限边界和下载行为。 */
class LegacyPageControllerTest {
    private HttpServer upstream;
    private MockMvc mvc;
    private final AtomicInteger calls = new AtomicInteger();
    private final AtomicReference<String> query = new AtomicReference<>();
    private final AtomicReference<String> body = new AtomicReference<>();
    private final AtomicReference<String> token = new AtomicReference<>();
    private final AtomicReference<String> operator = new AtomicReference<>();
    private int status = 200;
    private int delayMs;
    private byte[] reply = "{}".getBytes(StandardCharsets.UTF_8);

    @BeforeEach
    void start() throws Exception {
        upstream = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        upstream.createContext("/api", exchange -> {
            calls.incrementAndGet();
            if (delayMs > 0) {
                try { Thread.sleep(delayMs); } catch (InterruptedException interrupted) { Thread.currentThread().interrupt(); }
            }
            query.set(exchange.getRequestURI().getRawQuery());
            body.set(StreamUtils.copyToString(exchange.getRequestBody(), StandardCharsets.UTF_8));
            token.set(exchange.getRequestHeaders().getFirst("X-Integration-Token"));
            operator.set(exchange.getRequestHeaders().getFirst("X-Operator-Id"));
            exchange.getResponseHeaders().set("Content-Type", "application/json;charset=UTF-8");
            exchange.getResponseHeaders().set("Content-Disposition", "attachment; filename=plans.csv");
            exchange.getResponseHeaders().set("Set-Cookie", "private=must-not-forward");
            exchange.getResponseHeaders().set("Location", "/outside");
            exchange.sendResponseHeaders(status, reply.length);
            exchange.getResponseBody().write(reply);
            exchange.close();
        });
        upstream.start();
        LegacyPythonProperties properties = new LegacyPythonProperties();
        properties.setBaseUrl("http://127.0.0.1:" + upstream.getAddress().getPort());
        properties.setReadTimeoutMs(500);
        properties.setIntegrationToken("configured-test-token");
        properties.setOperatorId("configured-test-operator");
        mvc = MockMvcBuilders.standaloneSetup(new LegacyPageController(
                new LegacyPythonConfiguration().legacyPythonHttp(properties), properties)).build();
    }

    @AfterEach
    void stop() { upstream.stop(0); }

    @Test
    void preservesEncodedAndRepeatedQueries() throws Exception {
        mvc.perform(get(URI.create("/api/plan/items?name=%E4%B8%AD%E6%96%87&x=1&x=2")))
                .andExpect(status().isOk());
        assertThat(query.get()).isEqualTo("name=%E4%B8%AD%E6%96%87&x=1&x=2");
    }

    @Test
    void postsOriginalUtf8JsonAndReplacesUntrustedIdentity() throws Exception {
        String input = "{\"task_name\":\"测试策划\",\"account_ids\":[\"A1\"]}";
        status = 202;
        reply = "{\"status\":\"accepted\"}".getBytes(StandardCharsets.UTF_8);
        mvc.perform(post("/api/plan/manual-plans/previews").contentType("application/json")
                .header("X-Integration-Token", "browser-token").header("X-Operator-Id", "browser-operator")
                .content(input.getBytes(StandardCharsets.UTF_8)))
                .andExpect(status().isAccepted()).andExpect(content().bytes(reply));
        assertThat(body.get()).isEqualTo(input);
        assertThat(token.get()).isEqualTo("configured-test-token");
        assertThat(operator.get()).isEqualTo("configured-test-operator");
    }

    @Test
    void preservesBusinessConflictAndValidationErrors() throws Exception {
        for (int code : new int[] {409, 422, 503}) {
            status = code;
            reply = "{\"detail\":\"当前状态不可替换\"}".getBytes(StandardCharsets.UTF_8);
            mvc.perform(post("/api/plan/items/1/replace-topic").contentType("application/json").content("{}"))
                    .andExpect(status().is(code)).andExpect(content().bytes(reply));
        }
    }

    @Test
    void streamsDownloadWithoutForwardingCookies() throws Exception {
        reply = new byte[] {(byte) 0xef, (byte) 0xbb, (byte) 0xbf, 65, 44, 66, 13, 10};
        mvc.perform(post("/api/plan/query/export").contentType("application/json").content("{}"))
                .andExpect(status().isOk()).andExpect(content().bytes(reply))
                .andExpect(header().string("Content-Disposition", "attachment; filename=plans.csv"))
                .andExpect(header().doesNotExist("Set-Cookie"));
    }

    @Test
    void blocksInternalAndUnknownRoutesAndWrongMethodsBeforeCallingPython() throws Exception {
        for (String path : new String[] {"/api/plan/internal/wakeup", "/api/plan/integrations/bank/op04",
                "/api/plan/query/not-an-endpoint", "/api/plan/config/../internal/x",
                "/api/plan/manual-plans/marketing-tasks"}) {
            mvc.perform(post(path)).andExpect(status().isNotFound());
        }
        mvc.perform(delete("/api/plan/config")).andExpect(status().isNotFound());
        assertThat(calls.get()).isZero();
    }

    @Test
    void doesNotFollowRedirects() throws Exception {
        status = 302;
        mvc.perform(get("/api/plan/items")).andExpect(status().isFound());
        assertThat(calls.get()).isEqualTo(1);
    }

    @Test
    void reportsUnavailableUpstreamAsGatewayError() throws Exception {
        upstream.stop(0);
        mvc.perform(get("/api/plan/items")).andExpect(status().isBadGateway())
                .andExpect(jsonPath("$.detail").value("Python服务暂不可用"));
    }

    @Test
    void reportsReadTimeoutWithoutPretendingTheBusinessSucceeded() throws Exception {
        delayMs = 900;
        mvc.perform(get("/api/plan/items")).andExpect(status().isGatewayTimeout())
                .andExpect(jsonPath("$.detail").value("Python服务响应超时"));
    }

    @Test
    void rejectsAmbiguousPathsAndInvalidTargets() {
        for (String path : new String[] {"/api/plan/topics/a%2fb/detail", "/api/plan/topics/%252e/detail",
                "/api/plan/topics/../detail", "/api/plan/topics/a;param/detail"}) {
            assertThat(PageRoutes.allows("GET", path)).isFalse();
        }
        assertThat(PageRoutes.allows("GET", "/api/plan/topics/%E4%B8%AD%E6%96%87/detail")).isFalse();
        LegacyPythonProperties properties = new LegacyPythonProperties();
        for (String target : new String[] {"https://user:secret@host", "https://host/path", "https://host?key=x"}) {
            properties.setBaseUrl(target);
            org.junit.jupiter.api.Assertions.assertThrows(IllegalArgumentException.class, properties::baseUri);
        }
    }
}
