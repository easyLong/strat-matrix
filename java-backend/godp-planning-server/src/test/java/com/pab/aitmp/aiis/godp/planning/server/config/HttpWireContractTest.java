package com.pab.aitmp.aiis.godp.planning.server.config;

import static org.junit.jupiter.api.Assertions.*;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.pab.aitmp.aiis.godp.planning.entity.vo.req.BusinessPlanningConfig;
import com.pab.aitmp.aiis.godp.planning.entity.vo.req.ManualPreviewRequest;
import com.pab.aitmp.aiis.godp.planning.entity.vo.req.MarketingTaskRequest;
import com.pab.aitmp.aiis.godp.planning.server.controller.ManualPlanningController;
import java.time.LocalDate;
import java.util.Arrays;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ResponseStatus;

/** S1 moves Java packages; the page-facing names and accepted/created semantics stay stable. */
class HttpWireContractTest {
  private final ObjectMapper mapper = new ObjectMapper().findAndRegisterModules();

  @Test void postQueryMetadataDoesNotAccidentallyRequireResultPermissionsForManualCatalogs() throws Exception {
    Class<com.pab.aitmp.aiis.godp.planning.api.host.PlanningPermission> annotation=
        com.pab.aitmp.aiis.godp.planning.api.host.PlanningPermission.class;
    assertArrayEquals(new String[]{"manual.view","results.view"},ManualPlanningController.class
        .getMethod("accountsCatalog",com.pab.aitmp.aiis.godp.planning.entity.vo.req.CatalogQueryRequest.class)
        .getAnnotation(annotation).value());
    assertArrayEquals(new String[]{"manual.view"},ManualPlanningController.class
        .getMethod("availability",com.pab.aitmp.aiis.godp.planning.entity.vo.req.CatalogQueryRequest.class)
        .getAnnotation(annotation).value());
  }

  @Test void previewJsonRetainsExistingFieldNamesAndRoundTrips() throws Exception {
    ManualPreviewRequest request = mapper.readValue(
        "{\"task_name\":\"wire-test\",\"publish_date\":\"2026-11-09\","
            + "\"account_ids\":[\"A1\"],\"topic_ids\":[\"T1\"]}", ManualPreviewRequest.class);
    JsonNode json = mapper.valueToTree(request);
    assertEquals("wire-test", json.get("task_name").asText());
    assertEquals(LocalDate.of(2026, 11, 9), request.publish_date);
    assertEquals("A1", json.get("account_ids").get(0).asText());
    assertFalse(json.has("taskName"));
  }

  @Test void configAndMarketingRequestsRetainTheirWireContract() throws Exception {
    BusinessPlanningConfig config = mapper.readValue(
        "{\"planning_days\":[1,3,5],\"schedule_day\":2,\"schedule_time\":\"22:00\","
            + "\"marketing_max\":3,\"hotspot_ratio\":20,"
            + "\"content_production_lead_days\":{\"ordinary\":1,\"marketing\":0,\"hotspot\":1}}",
        BusinessPlanningConfig.class);
    JsonNode result = mapper.valueToTree(config);
    assertEquals(Arrays.asList(1,3,5), config.planning_days);
    assertEquals(1, result.get("content_production_lead_days").get("ordinary").asInt());
    assertFalse(result.has("planningDays"));
    MarketingTaskRequest request = mapper.readValue(
        "{\"task_name\":\"marketing-wire\",\"topic_id\":\"M1\",\"allocation_count\":2}",
        MarketingTaskRequest.class);
    assertEquals("marketing-wire", mapper.valueToTree(request).get("task_name").asText());
    assertEquals(2, mapper.valueToTree(request).get("allocation_count").asInt());
  }

  @Test void submissionResponseStillMeansAcceptedRatherThanCompleted() throws Exception {
    assertEquals(HttpStatus.CREATED, ManualPlanningController.class
        .getMethod("preview", ManualPreviewRequest.class).getAnnotation(ResponseStatus.class).value());
    assertEquals(HttpStatus.ACCEPTED, ManualPlanningController.class
        .getMethod("submit", String.class).getAnnotation(ResponseStatus.class).value());
  }
}
