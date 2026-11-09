package com.pab.aitmp.aiis.godp.digital.marketing.server.xiangliang.dev;
import static org.junit.jupiter.api.Assertions.*;
import java.util.*;
import java.util.concurrent.atomic.*;
import org.junit.jupiter.api.Test;

class LocalJobPulseTest {
  @Test void oneTimerInvokesFourHandlersOnlyWhenDueAndRetriesFailedPasses() {
    AtomicLong now=new AtomicLong();
    Map<String,AtomicInteger> counts=new LinkedHashMap<>();
    Map<String,Runnable> handlers=new LinkedHashMap<>();
    for(String name:Arrays.asList("manual","automatic","content","hotspot")) {
      AtomicInteger calls=new AtomicInteger();counts.put(name,calls);
      handlers.put(name,() -> { if(calls.incrementAndGet()==1 && name.equals("manual")) throw new IllegalStateException(); });
    }
    LocalJobPulse pulse=new LocalJobPulse(handlers,now::get); pulse.pulse();
    now.set(1000);pulse.pulse();
    assertEquals(2,counts.get("manual").get());assertEquals(1,counts.get("automatic").get());
    now.set(2000);pulse.pulse();assertEquals(2,counts.get("manual").get());
    now.set(3000);pulse.pulse();assertEquals(3,counts.get("manual").get());
    now.set(60000);pulse.pulse();
    assertEquals(2,counts.get("automatic").get());assertEquals(2,counts.get("content").get());
    assertEquals(2,counts.get("hotspot").get());
  }
  @Test void incompleteHandlerConfigurationDoesNotStartSilently() {
    assertThrows(IllegalArgumentException.class,() -> new LocalJobPulse(Collections.emptyMap()));
  }
}
