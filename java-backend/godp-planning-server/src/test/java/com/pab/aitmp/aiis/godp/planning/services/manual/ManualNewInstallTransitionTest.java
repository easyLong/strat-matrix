package com.pab.aitmp.aiis.godp.planning.services.manual;

import com.pab.aitmp.aiis.godp.planning.api.port.ManualPorts;
import com.pab.aitmp.aiis.godp.planning.entity.error.BusinessException;
import com.pab.aitmp.aiis.godp.planning.entity.support.Json;

import static org.junit.jupiter.api.Assertions.*;

import java.util.Collections;
import org.junit.jupiter.api.Test;

class ManualNewInstallTransitionTest {
  @Test
  void emptyInstallationHasNoHistoricalRowsAndRejectsOldIds() {
    ManualPorts.Transition transition = new ManualNewInstallTransition();
    assertEquals(0, Json.number(transition.queryPage("plans", Json.map()), "total"));
    assertEquals(Collections.emptyList(), transition.batches(20, null));
    assertEquals(0, transition.resultWatermark());
    BusinessException missing = assertThrows(BusinessException.class, () -> transition.batch(1));
    assertEquals(404, missing.status);
    assertThrows(BusinessException.class, () -> transition.replaceTopic(1, Json.map()));
  }
}
