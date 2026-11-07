package com.pab.aitmp.aiis.godp.planning.server.config;

import com.sun.net.httpserver.HttpServer;
import java.net.*;
import java.util.concurrent.*;
import org.springframework.http.HttpMethod;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockMvcRequestBuilders;
import org.springframework.util.StreamUtils;

/**
 * Optional browser bridge: loopback-only, test JVM only, all requests execute real MVC handlers.
 */
final class InsideBrowserBridge {
  static void run(MockMvc mvc) throws Exception {
    if (!"1".equals(System.getenv("PLANNING_BROWSER_ACCEPTANCE"))) return;
    HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
    ExecutorService executor = Executors.newFixedThreadPool(2);
    server.setExecutor(executor);
    server.createContext(
        "/",
        exchange -> {
          try {
            org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder request =
                MockMvcRequestBuilders.request(
                    HttpMethod.valueOf(exchange.getRequestMethod()), exchange.getRequestURI());
            exchange
                .getRequestHeaders()
                .forEach((name, values) -> values.forEach(value -> request.header(name, value)));
            request.content(StreamUtils.copyToByteArray(exchange.getRequestBody()));
            org.springframework.mock.web.MockHttpServletResponse response =
                mvc.perform(request).andReturn().getResponse();
            for (String name : response.getHeaderNames())
              exchange
                  .getResponseHeaders()
                  .put(name, new java.util.ArrayList<>(response.getHeaders(name)));
            byte[] body = response.getContentAsByteArray();
            exchange.sendResponseHeaders(response.getStatus(), body.length);
            exchange.getResponseBody().write(body);
          } catch (Exception failure) {
            exchange.sendResponseHeaders(500, -1);
          } finally {
            exchange.close();
          }
        });
    server.start();
    Process browser = null;
    try {
      browser =
          new ProcessBuilder(
                  "node",
                  java.nio.file.Paths.get(System.getProperty("planning.repository-root", ".."),
                      "frontend/tests/inside-pages.browser.cjs").toAbsolutePath().normalize().toString(),
                  "http://127.0.0.1:" + server.getAddress().getPort())
              .inheritIO()
              .start();
      if (!browser.waitFor(90, TimeUnit.SECONDS)) {
        browser.destroyForcibly();
        throw new AssertionError("Browser acceptance timed out");
      }
      if (browser.exitValue() != 0) throw new AssertionError("Browser acceptance failed");
    } finally {
      if (browser != null && browser.isAlive()) browser.destroyForcibly();
      server.stop(0);
      executor.shutdownNow();
    }
  }
}
