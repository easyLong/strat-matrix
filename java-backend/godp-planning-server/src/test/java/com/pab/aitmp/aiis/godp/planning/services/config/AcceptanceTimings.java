package com.pab.aitmp.aiis.godp.planning.services.config;

import com.pab.aitmp.aiis.godp.planning.entity.support.Json;

import static com.pab.aitmp.aiis.godp.planning.entity.support.Json.*;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.time.Instant;
import java.util.function.Supplier;

/** Test-only timing; never records request bodies, headers, SQL, URLs or exception messages. */
final class AcceptanceTimings {
  private final Path output;

  AcceptanceTimings(Path directory, boolean enabled) {
    output = enabled ? directory.resolve("java-timings.jsonl") : null;
  }

  <T> T call(String name, Supplier<T> action) {
    long started = System.nanoTime();
    Instant at = Instant.now();
    String status = "ok";
    try {
      return action.get();
    } catch (RuntimeException error) {
      status = "error";
      throw error;
    } finally {
      record(name, started, at, status);
    }
  }

  synchronized void record(String name, long started, Instant at, String status) {
    if (output == null) return;
    String line =
        write(
                map(
                    "name", name,
                    "started_at", at.toString(),
                    "duration_s", (System.nanoTime() - started) / 1_000_000_000.0,
                    "status", status))
            + "\n";
    try {
      Files.write(
          output,
          line.getBytes(StandardCharsets.UTF_8),
          StandardOpenOption.CREATE,
          StandardOpenOption.APPEND);
    } catch (IOException error) {
      throw new IllegalStateException("Acceptance timing could not be saved");
    }
  }
}
