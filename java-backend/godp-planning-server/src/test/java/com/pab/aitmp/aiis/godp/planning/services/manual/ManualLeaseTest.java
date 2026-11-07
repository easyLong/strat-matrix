package com.pab.aitmp.aiis.godp.planning.services.manual;

import static org.junit.jupiter.api.Assertions.*;
import static com.pab.aitmp.aiis.godp.planning.entity.support.Json.*;
import java.util.*;
import java.util.concurrent.*;
import org.junit.jupiter.api.*;
import org.springframework.transaction.support.TransactionSynchronizationManager;

class ManualLeaseTest {
  ManualClosureTest fixture;
  long id;
  @BeforeEach void setup() {
    fixture=new ManualClosureTest(); fixture.setup();
    id=number(fixture.task("2026-11-20"),"id");
  }
  @Test void twoInstancesCannotOwnTheSameUnexpiredTask() throws Exception {
    ExecutorService pool=Executors.newFixedThreadPool(2);
    try {
      Future<Map<String,Object>> a=pool.submit(() -> fixture.repo.claimTask(id,"worker-a",1000,5000));
      Future<Map<String,Object>> b=pool.submit(() -> fixture.repo.claimTask(id,"worker-b",1000,5000));
      assertEquals(1,(a.get(5,TimeUnit.SECONDS)==null ? 0:1)+(b.get(5,TimeUnit.SECONDS)==null ? 0:1));
      assertNotNull(object(read(text(fixture.repo.taskById(id),"payload")).get("input")));
    } finally { pool.shutdownNow(); }
  }
  @Test void expiredLeaseRecoversAndLateOwnerCannotWriteOrRelease() {
    assertNotNull(fixture.repo.claimTask(id,"old",1000,1000));
    assertNull(fixture.repo.claimTask(id,"new",1999,1000));
    assertNotNull(fixture.repo.claimTask(id,"new",2001,1000));
    fixture.repo.withClaim(id,"old",() -> fixture.repo.markFailed(id,"late",3000));
    fixture.repo.releaseClaim(id,"old");
    assertEquals("pending",fixture.repo.taskById(id).get("status"));
    fixture.repo.withClaim(id,"new",() -> fixture.repo.markComputing(id,3000));
    assertEquals("computing",fixture.repo.taskById(id).get("status"));
    fixture.repo.releaseClaim(id,"new");
    assertNotNull(fixture.repo.claimTask(id,"third",4000,1000));
  }
  @Test void failedDatabaseUnitRollsBackAndRemoteComputeHoldsNoTransaction() {
    fixture.repo.claimTask(id,"owner",1000,1000);
    assertThrows(IllegalStateException.class,() -> fixture.repo.withClaim(id,"owner",() -> {
      fixture.repo.markFailed(id,"rollback",1500); throw new IllegalStateException("failure");
    }));
    assertEquals("pending",fixture.repo.taskById(id).get("status"));
    fixture.repo.releaseClaim(id,"owner");
    ManualPlanningService worker=new ManualPlanningService(fixture.repo,fixture.fixture,input -> {
      assertFalse(TransactionSynchronizationManager.isActualTransactionActive());
      return fixture.fixture.submit(input);
    },() -> "trusted-actor");
    worker.advance();
    assertEquals("completed",fixture.repo.taskById(id).get("status"));
    assertEquals(2,fixture.repo.items().size());
  }
}
