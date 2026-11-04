package com.stratmatrix.planning.host;

import static com.stratmatrix.planning.manual.Json.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import com.stratmatrix.planning.api.PlanningApiErrors;
import com.stratmatrix.planning.context.*;
import com.stratmatrix.planning.manual.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.util.TestPropertyValues;
import org.springframework.context.annotation.*;
import org.springframework.mock.web.MockServletContext;
import org.springframework.test.web.servlet.*;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.context.support.AnnotationConfigWebApplicationContext;
import org.springframework.web.servlet.config.annotation.EnableWebMvc;

class HostRequestContextTest {
  @Configuration
  @EnableWebMvc
  @Import({HostWebConfiguration.class, PlanningApiErrors.class})
  static class Host {
    @Bean
    AtomicInteger contextCalls() {
      return new AtomicInteger();
    }

    @Bean
    ManualPorts.Actor actor() {
      return () -> "FALLBACK";
    }

    @Bean
    HostAccess access() {
      return request -> {
        if ("yes".equals(request.getHeader("X-Deny"))) throw new BusinessException(403, "无访问权限");
      };
    }

    @Bean
    HostContextProvider contexts(AtomicInteger calls) {
      return request -> {
        calls.incrementAndGet();
        return new PlanningRequestContext(
            "TRUSTED",
            PlanningRequestContext.Scope.ORGANIZATIONS,
            Collections.singleton("ORG02"),
            "host-trace-1");
      };
    }

    @Bean
    Demo demo() {
      return new Demo();
    }
  }

  @RestController
  static class Demo {
    @GetMapping("/api/plan/context")
    Object context() {
      PlanningRequestContext ctx = RequestContexts.require();
      return map(
          "um",
          RequestContexts.actor(() -> "WRONG").current(),
          "scope",
          ctx.scope,
          "organizations",
          ctx.organizationCodes);
    }

    @GetMapping("/api/plan/fault")
    Object fault() {
      throw new IllegalStateException("private connection secret");
    }

    @GetMapping("/api/plan/async")
    Callable<Object> async() {
      return () -> {
        assertFalse(RequestContexts.current().isPresent());
        return map("ok", true);
      };
    }
  }

  @Test
  void trustedContextIsUsedAndCleanedAfterSuccessDenialFailureAndAsync() throws Exception {
    try (AnnotationConfigWebApplicationContext app = new AnnotationConfigWebApplicationContext()) {
      app.setServletContext(new MockServletContext());
      app.getEnvironment().setActiveProfiles("inside");
      TestPropertyValues.of("planning.host.enabled=true").applyTo(app);
      app.register(Host.class);
      app.refresh();
      MockMvc mvc = MockMvcBuilders.webAppContextSetup(app).build();
      mvc.perform(
              get("/api/plan/context")
                  .header("X-User-UM", "FORGED")
                  .header("X-Request-Id", "FORGED"))
          .andExpect(status().isOk())
          .andExpect(jsonPath("$.um").value("TRUSTED"))
          .andExpect(jsonPath("$.organizations[0]").value("ORG02"))
          .andExpect(header().string("X-Request-Id", "host-trace-1"));
      assertFalse(RequestContexts.current().isPresent());
      mvc.perform(get("/api/plan/context").header("X-Deny", "yes"))
          .andExpect(status().isForbidden());
      assertEquals(1, app.getBean(AtomicInteger.class).get());
      assertFalse(RequestContexts.current().isPresent());
      mvc.perform(get("/api/plan/fault"))
          .andExpect(status().isInternalServerError())
          .andExpect(jsonPath("$.detail").value("服务处理异常，请联系管理员并提供请求追踪号"))
          .andExpect(header().string("X-Request-Id", "host-trace-1"));
      assertFalse(RequestContexts.current().isPresent());
      MvcResult pending =
          mvc.perform(get("/api/plan/async")).andExpect(request().asyncStarted()).andReturn();
      assertFalse(RequestContexts.current().isPresent());
      mvc.perform(asyncDispatch(pending))
          .andExpect(status().isOk())
          .andExpect(jsonPath("$.ok").value(true));
      assertFalse(RequestContexts.current().isPresent());
    }
  }

  @Test
  void scopesAreImmutableNestedAndNotInheritedByBackgroundThreads() throws Exception {
    List<String> codes = new ArrayList<>(Collections.singleton("ORG02"));
    PlanningRequestContext outer =
        new PlanningRequestContext("UM1", PlanningRequestContext.Scope.ORGANIZATIONS, codes, null);
    codes.clear();
    assertEquals(1, outer.organizationCodes.size());
    assertThrows(UnsupportedOperationException.class, () -> outer.organizationCodes.clear());
    assertThrows(
        IllegalArgumentException.class,
        () ->
            new PlanningRequestContext(
                "UM", PlanningRequestContext.Scope.ALL, Collections.singleton("ORG"), null));
    assertThrows(
        IllegalArgumentException.class,
        () ->
            new PlanningRequestContext(
                "UM", PlanningRequestContext.Scope.NONE, Collections.emptyList(), "bad\r\nheader"));
    ExecutorService pool = Executors.newSingleThreadExecutor();
    try (RequestContexts.Scope ignored = RequestContexts.open(outer)) {
      try (RequestContexts.Scope inner =
          RequestContexts.open(PlanningRequestContext.identity("UM2"))) {
        assertEquals("UM2", RequestContexts.require().userUm);
      }
      assertSame(outer, RequestContexts.require());
      assertFalse(
          pool.submit(() -> RequestContexts.current().isPresent()).get(3, TimeUnit.SECONDS));
    } finally {
      pool.shutdownNow();
    }
    assertFalse(RequestContexts.current().isPresent());
    assertThrows(BusinessException.class, RequestContexts::require);
    assertEquals("EXPLICIT-JOB-ACTOR", RequestContexts.actor(() -> "EXPLICIT-JOB-ACTOR").current());
  }
}
