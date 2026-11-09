package com.pab.aitmp.aiis.godp.digital.marketing.server.xiangliang.dev;

import com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.port.PlanningJobHandler;
import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.vo.req.PlanningJobRequest;
import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.vo.res.PlanningJobResult;
import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.tasks.*;
import java.time.Instant;
import java.util.*;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.*;
import org.springframework.scheduling.annotation.EnableScheduling;

/** Never imported by the host. Host trigger frequency and durable cursors belong to its scheduler. */
@Configuration("xiangliangLocalExecutionConfiguration")
@Profile("local & !inside")
@ConditionalOnProperty(name={"planning.local-pulse.enabled","planning.tasks.enabled"},havingValue="true")
@EnableScheduling
public class LocalExecutionConfiguration {
  @Bean(name="xiangliangLocalJobPulse") public LocalJobPulse localJobPulse(ManualTaskAdvanceHandler manual,AutoScheduleHandler automatic,
      ContentCompletionHandler content,HotspotCheckHandler hotspot) {
    Map<String,Runnable> actions=new LinkedHashMap<>();
    actions.put("manual",pass(manual)); actions.put("automatic",pass(automatic));
    actions.put("content",pass(content));
    LocalDailyHotspotCheck daily=new LocalDailyHotspotCheck((now,after) -> {
      PlanningJobResult result=hotspot.run(new PlanningJobRequest(now,100,Collections.singletonMap("HOTSPOT",after),false));
      if("retry_required".equals(result.status)) throw new IllegalStateException("Hotspot retry required");
      return result.phases.get(0);
    });
    actions.put("hotspot",() -> daily.run(Instant.now()));
    return new LocalJobPulse(actions);
  }
  private static Runnable pass(PlanningJobHandler handler) {
    Map<String,Long> cursors=new LinkedHashMap<>();
    return () -> {
      // Content flow is intentionally excluded: its writer is triggered by three explicit daily host jobs.
      PlanningJobResult result=handler.run(new PlanningJobRequest(Instant.now(),100,cursors,false));
      cursors.clear(); cursors.putAll(result.nextCursors);
      if("retry_required".equals(result.status)) throw new IllegalStateException("Planning pass needs retry");
    };
  }
}
