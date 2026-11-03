package com.stratmatrix.standalone;

import static org.mockito.Mockito.*;

import com.stratmatrix.planning.adapter.python.PythonExecutionClient;
import java.util.Arrays;
import java.util.Collections;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import org.junit.jupiter.api.Test;

class LocalJobPulseTest {
  @Test
  void migratedBusinessOnlyWakesAlgorithmJobs() {
    PythonExecutionClient client = mock(PythonExecutionClient.class);
    LocalJobPulse pulse = new LocalJobPulse(client, () -> 0L);
    pulse.enableJavaBusinessOwnership();
    pulse.enableJavaWeekly(() -> {});
    pulse.pulse();
    verify(client).wakeup(Arrays.asList("planning", "manual_compute"));
  }

  @Test
  void javaWeeklyTriggerReplacesPythonWeeklyPulse() {
    AtomicLong now = new AtomicLong();
    AtomicInteger javaTicks = new AtomicInteger();
    PythonExecutionClient client = mock(PythonExecutionClient.class);
    LocalJobPulse pulse = new LocalJobPulse(client, now::get);
    pulse.enableJavaWeekly(javaTicks::incrementAndGet);
    pulse.pulse();
    verify(client).wakeup(Arrays.asList("manual", "planning", "hotspot"));
    org.junit.jupiter.api.Assertions.assertEquals(1, javaTicks.get());
    now.set(60000);
    pulse.pulse();
    org.junit.jupiter.api.Assertions.assertEquals(2, javaTicks.get());
    verify(client, times(2)).wakeup(Arrays.asList("manual", "planning", "hotspot"));
  }

  @Test
  void triggersOnlyDueJobsAndRetriesUnacknowledgedWork() {
    AtomicLong now = new AtomicLong();
    PythonExecutionClient client = mock(PythonExecutionClient.class);
    LocalJobPulse pulse = new LocalJobPulse(client, now::get);
    doThrow(new IllegalStateException())
        .doNothing()
        .when(client)
        .wakeup(Arrays.asList("manual", "planning", "weekly", "hotspot"));
    pulse.pulse();
    now.set(1000);
    pulse.pulse();
    verify(client, times(2)).wakeup(Arrays.asList("manual", "planning", "weekly", "hotspot"));
    now.set(2000);
    pulse.pulse();
    verifyNoMoreInteractions(client);
    now.set(3000);
    pulse.pulse();
    verify(client).wakeup(Collections.singletonList("manual"));
  }
}
