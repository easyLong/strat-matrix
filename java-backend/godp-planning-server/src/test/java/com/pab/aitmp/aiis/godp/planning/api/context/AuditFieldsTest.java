package com.pab.aitmp.aiis.godp.planning.api.context;

import com.pab.aitmp.aiis.godp.planning.entity.context.PlanningRequestContext;

import static org.junit.jupiter.api.Assertions.*;

import com.pab.aitmp.aiis.godp.planning.entity.error.BusinessException;
import java.util.*;
import org.junit.jupiter.api.Test;

class AuditFieldsTest {
  @Test
  void usesTrustedUmAndNeverAttributesABackgroundUpdateToTheOriginalCreator() {
    Map<String, Object> args = new HashMap<>();
    args.put("payload", "{\"created_by\":\"old-creator\"}");
    assertEquals("old-creator", AuditFields.actor(args, true));
    assertEquals("system", AuditFields.actor(args, false));
    try (RequestContexts.Scope ignored =
        RequestContexts.open(PlanningRequestContext.identity("TRUSTED-UM"))) {
      assertEquals("TRUSTED-UM", AuditFields.actor(args, false));
      assertEquals("TRUSTED-UM", AuditFields.actor(args, true));
    }
  }

  @Test
  void rejectsOversizeActorsInsteadOfTruncatingAnAuditIdentity() {
    Map<String, Object> args = new HashMap<>();
    args.put("actor", String.join("", Collections.nCopies(51, "x")));
    assertThrows(BusinessException.class, () -> AuditFields.actor(args, true));
    args.put("actor", "VALID-UM");
    assertEquals("VALID-UM", AuditFields.actor(args, false));
  }
}
