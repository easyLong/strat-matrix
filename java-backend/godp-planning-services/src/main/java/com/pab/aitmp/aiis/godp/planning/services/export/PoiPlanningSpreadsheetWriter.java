package com.pab.aitmp.aiis.godp.planning.services.export;
import com.pab.aitmp.aiis.godp.planning.api.port.PlanningSpreadsheetWriter;
import java.util.List;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import org.apache.poi.ss.usermodel.*;
import org.apache.poi.ss.util.CellRangeAddress;
import org.apache.poi.xssf.streaming.SXSSFWorkbook;

/** Public-dependency development adapter; replace this one bean with the host Excel library. */
public final class PoiPlanningSpreadsheetWriter implements PlanningSpreadsheetWriter {
  public byte[] write(List<String> headers, List<List<String>> rows) {
    SXSSFWorkbook book = new SXSSFWorkbook(200);
    book.setCompressTempFiles(true);
    try (ByteArrayOutputStream out = new ByteArrayOutputStream()) {
      Sheet sheet = book.createSheet("策划明细");
      sheet.createFreezePane(0, 1);
      CellStyle heading = book.createCellStyle();
      heading.setFillForegroundColor(IndexedColors.DARK_BLUE.getIndex());
      heading.setFillPattern(FillPatternType.SOLID_FOREGROUND);
      Font font = book.createFont();
      font.setBold(true);
      font.setColor(IndexedColors.WHITE.getIndex());
      heading.setFont(font);
      Row header = sheet.createRow(0);
      for (int col = 0; col < headers.size(); col++) {
        Cell cell = header.createCell(col, CellType.STRING);
        cell.setCellValue(headers.get(col));
        cell.setCellStyle(heading);
        sheet.setColumnWidth(col, (col == 6 || col == 7 || col == 13 ? 36 : 20) * 256);
      }
      int rowNumber = 1;
      for (List<String> values : rows) {
        Row sheetRow = sheet.createRow(rowNumber++);
        for (int col = 0; col < values.size(); col++)
          sheetRow.createCell(col, CellType.STRING).setCellValue(SpreadsheetCells.safe(values.get(col)));
      }
      sheet.setAutoFilter(
          new CellRangeAddress(0, Math.max(0, rowNumber - 1), 0, headers.size() - 1));
      book.write(out);
      return out.toByteArray();
    } catch (IOException e) {
      throw new IllegalStateException("策划明细导出失败", e);
    } finally {
      book.dispose();
      try {
        book.close();
      } catch (IOException ignored) {
        /* temporary files already disposed */
      }
    }
  }
}
