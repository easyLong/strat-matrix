package com.pab.aitmp.aiis.godp.planning.server.web;

import com.pab.aitmp.aiis.godp.planning.services.config.*;
import com.pab.aitmp.aiis.godp.planning.api.context.*;
import com.pab.aitmp.aiis.godp.planning.services.manual.*;
import com.pab.aitmp.aiis.godp.planning.services.source.*;

import com.pab.aitmp.aiis.godp.planning.api.context.RequestContexts;
import com.pab.aitmp.aiis.godp.planning.api.port.ManualPorts;
import com.pab.aitmp.aiis.godp.planning.api.port.SourceFacts;
import com.pab.aitmp.aiis.godp.planning.api.response.PlanningResponseAdapter;
import com.pab.aitmp.aiis.godp.planning.entity.context.PlanningRequestContext;
import com.pab.aitmp.aiis.godp.planning.entity.entity.BusinessPlanningConfigRow;
import com.pab.aitmp.aiis.godp.planning.entity.error.BusinessException;
import com.pab.aitmp.aiis.godp.planning.entity.error.PlanningValidationException;
import com.pab.aitmp.aiis.godp.planning.entity.support.Json;
import com.pab.aitmp.aiis.godp.planning.entity.vo.req.BusinessPlanningConfig;
import com.pab.aitmp.aiis.godp.planning.server.controller.BusinessPlanningConfigController;
import com.pab.aitmp.aiis.godp.planning.server.controller.ManualPlanningController;
import com.pab.aitmp.aiis.godp.planning.server.controller.SourceFactsController;
import com.pab.aitmp.aiis.godp.planning.services.config.BusinessPlanningConfigMapper;
import com.pab.aitmp.aiis.godp.planning.services.config.BusinessPlanningConfigService;
import com.pab.aitmp.aiis.godp.planning.services.manual.ManualExportService;
import com.pab.aitmp.aiis.godp.planning.services.manual.ManualItemService;
import com.pab.aitmp.aiis.godp.planning.services.manual.ManualPlanningService;
import com.pab.aitmp.aiis.godp.planning.services.manual.ManualQueryService;
import com.pab.aitmp.aiis.godp.planning.services.manual.ManualRepository;
import com.pab.aitmp.aiis.godp.planning.services.manual.MarketingTaskService;

import static com.pab.aitmp.aiis.godp.planning.entity.support.Json.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import java.nio.charset.StandardCharsets;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.springframework.dao.DataAccessResourceFailureException;
import org.springframework.http.*;
import org.springframework.test.web.servlet.*;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.client.ResourceAccessException;

class PlanningApiBoundaryTest {
  private BusinessPlanningConfigService.Result result(int version) {
    BusinessPlanningConfigMapper mapper = mock(BusinessPlanningConfigMapper.class);
    BusinessPlanningConfigRow row = new BusinessPlanningConfigRow();
    row.version = version;
    row.planningDays = "1,3,5";
    when(mapper.current()).thenReturn(row);
    return new BusinessPlanningConfigService(
            mapper, mock(org.springframework.transaction.PlatformTransactionManager.class))
        .current();
  }

  private PlanningResponseAdapter envelope() {
    return new PlanningResponseAdapter() {
      public Object success(Object body) {
        return map("code", "OK", "data", body);
      }

      public ResponseEntity<?> error(Failure failure) {
        return ResponseEntity.status(failure.status)
            .body(
                map("code", failure.code, "message", failure.message, "trace_id", failure.traceId));
      }
    };
  }

  private MockMvc mvc(PlanningResponseAdapter adapter, Object... controllers) {
    return MockMvcBuilders.standaloneSetup(controllers)
        .setControllerAdvice(new PlanningApiErrors(adapter), new PlanningApiResponseAdvice(adapter))
        .build();
  }

  @Test
  void defaultWireFormatAndHostWrapperUseOneBoundaryAndTrustedActor() throws Exception {
    BusinessPlanningConfigService.Result first = result(2), saved = result(3);
    BusinessPlanningConfigService service = mock(BusinessPlanningConfigService.class);
    when(service.current()).thenReturn(first);
    BusinessPlanningConfigController controller =
        new BusinessPlanningConfigController(service, () -> "FALLBACK");
    mvc(new PlanningResponseAdapter() {}, controller)
        .perform(post("/api/plan/business-config/query").contentType(MediaType.APPLICATION_JSON).content("{}"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.version").value(2))
        .andExpect(jsonPath("$.data").doesNotExist());
    MockMvc custom = mvc(envelope(), controller);
    custom
        .perform(post("/api/plan/business-config/query").contentType(MediaType.APPLICATION_JSON).content("{}"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.code").value("OK"))
        .andExpect(jsonPath("$.data.version").value(2));
    when(service.save(any(BusinessPlanningConfig.class), eq(2), eq("TRUSTED"))).thenReturn(saved);
    try (RequestContexts.Scope ignored =
        RequestContexts.open(
            new PlanningRequestContext(
                "TRUSTED",
                PlanningRequestContext.Scope.NONE,
                Collections.emptyList(),
                "trace-test"))) {
      custom
          .perform(
              post("/api/plan/business-config/save")
                  .header("X-User-UM", "FORGED")
                  .contentType(MediaType.APPLICATION_JSON)
                  .content("{\"config\":{},\"expectedVersion\":2}"))
          .andExpect(status().isOk())
          .andExpect(jsonPath("$.data.version").value(3));
      verify(service).save(any(BusinessPlanningConfig.class), eq(2), eq("TRUSTED"));
      when(service.current()).thenThrow(new BusinessException(409, "版本冲突"));
      custom
          .perform(post("/api/plan/business-config/query").contentType(MediaType.APPLICATION_JSON).content("{}"))
          .andExpect(status().isConflict())
          .andExpect(jsonPath("$.code").value("BUSINESS_ERROR"))
          .andExpect(jsonPath("$.data").doesNotExist())
          .andExpect(header().string("X-Request-Id", "trace-test"));
    }
  }

  @Test
  void validationDependenciesAndUnexpectedFailuresAreCentralAndDoNotExposeInternals()
      throws Exception {
    BusinessPlanningConfigService service = mock(BusinessPlanningConfigService.class);
    MockMvc mvc =
        mvc(
            new PlanningResponseAdapter() {},
            new BusinessPlanningConfigController(service, () -> "UM"));
    RuntimeException[] failures = {
      new PlanningValidationException("每周策划日至少选择一天"),
      new IllegalArgumentException("private SQL/credential"),
      new DataAccessResourceFailureException("private db"),
      new ResourceAccessException("private connection"),
      new IllegalStateException("private key")
    };
    int[] statuses = {422, 422, 503, 503, 500};
    for (int i = 0; i < failures.length; i++) {
      doThrow(failures[i]).when(service).current();
      MvcResult result =
          mvc.perform(post("/api/plan/business-config/query").contentType(MediaType.APPLICATION_JSON).content("{}"))
              .andExpect(status().is(statuses[i]))
              .andExpect(header().exists("X-Request-Id"))
              .andReturn();
      assertFalse(
          result.getResponse().getContentAsString(StandardCharsets.UTF_8).contains("private"));
    }
    mvc.perform(
            post("/api/plan/business-config/save")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{"))
        .andExpect(status().isUnprocessableEntity());
    mvc.perform(
            post("/api/plan/business-config/save").contentType(MediaType.APPLICATION_JSON).content("{}"))
        .andExpect(status().isUnprocessableEntity());
    mvc.perform(post("/api/plan/business-config")).andExpect(status().isNotFound());
  }

  @Test
  void standaloneBusinessPostValidatesBodyAndRetainsUnifiedReleaseGuard() throws Exception {
    BusinessPlanningConfigService.Result current = result(2), saved = result(3);
    BusinessPlanningConfigService service = mock(BusinessPlanningConfigService.class);
    when(service.current()).thenReturn(current);
    when(service.save(any(BusinessPlanningConfig.class), eq(2), eq("HOST-UM"))).thenReturn(saved);
    BusinessPlanningConfigController controller = new BusinessPlanningConfigController(service, () -> "HOST-UM");
    MockMvc http = mvc(envelope(), controller);
    http.perform(post("/api/plan/business-config/query").contentType(MediaType.APPLICATION_JSON).content("{}"))
        .andExpect(status().isOk()).andExpect(jsonPath("$.data.version").value(2));
    http.perform(post("/api/plan/business-config/versions/query").contentType(MediaType.APPLICATION_JSON).content("{\"limit\":0}"))
        .andExpect(status().isUnprocessableEntity());
    verify(service, never()).versions(anyInt());
    for (String invalid : Arrays.asList("{}", "{\"config\":{},\"expectedVersion\":-1}"))
      http.perform(post("/api/plan/business-config/save").contentType(MediaType.APPLICATION_JSON).content(invalid))
          .andExpect(status().isUnprocessableEntity());
    verify(service, never()).save(any(), anyInt(), anyString());
    String input = "{\"config\":{},\"expectedVersion\":2}";
    http.perform(post("/api/plan/business-config/save").contentType(MediaType.APPLICATION_JSON).content(input))
        .andExpect(status().isOk()).andExpect(jsonPath("$.data.version").value(3));
    verify(service).save(any(BusinessPlanningConfig.class), eq(2), eq("HOST-UM"));
    org.springframework.test.util.ReflectionTestUtils.setField(controller, "combinedRelease", true);
    http.perform(post("/api/plan/business-config/save").contentType(MediaType.APPLICATION_JSON).content(input))
        .andExpect(status().isConflict());
    verify(service, times(1)).save(any(), anyInt(), anyString());
  }

  @Test
  void sourceMachineErrorsAndResultsRemainStableEvenWhenPageResponsesAreWrapped() throws Exception {
    SourceFacts facts = mock(SourceFacts.class);
    when(facts.accounts(anyMap()))
        .thenReturn(
            map("items", Collections.emptyList(), "total", 0, "page_no", 1, "page_size", 100));
    MockMvc mvc =
        mvc(
            envelope(),
            new SourceFactsController(facts, mock(ManualRepository.class), "source-token"));
    mvc.perform(
            post("/api/plan/internal/source/accounts/query")
                .header("X-Integration-Token", "source-token")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{}"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.total").value(0))
        .andExpect(jsonPath("$.data").doesNotExist());
    mvc.perform(
            post("/api/plan/internal/source/accounts/query")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{}"))
        .andExpect(status().isUnauthorized())
        .andExpect(jsonPath("$.detail").value("Java资料查询认证失败"))
        .andExpect(jsonPath("$.code").doesNotExist());
  }

  @Test
  void binaryExportsStayByteIdenticalAndValidationStillReturnsJson() throws Exception {
    ManualExportService exports = mock(ManualExportService.class);
    byte[] file = {80, 75, 3, 4, 0, 1};
    when(exports.export(anyMap())).thenReturn(file);
    ManualPlanningController controller =
        new ManualPlanningController(
            mock(ManualPlanningService.class),
            mock(ManualQueryService.class),
            mock(ManualItemService.class),
            exports,
            mock(ManualPorts.Source.class),
            mock(ManualPorts.Transition.class),
            mock(MarketingTaskService.class));
    MockMvc mvc = mvc(envelope(), controller);
    mvc.perform(
            post("/api/plan/query/export")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"format\":\"xlsx\"}"))
        .andExpect(status().isOk())
        .andExpect(content().bytes(file))
        .andExpect(header().string("Content-Disposition", "attachment; filename=planning.xlsx"));
    mvc.perform(
            post("/api/plan/manual-plans/previews")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{}"))
        .andExpect(status().isUnprocessableEntity())
        .andExpect(jsonPath("$.code").value("VALIDATION_ERROR"));
  }
}
