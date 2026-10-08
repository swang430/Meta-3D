from pypdf import PdfReader
import pytest

from app.services.pdf_generator import PDFGenerator


def test_report_embeds_chinese_body_and_distinct_bold_face_from_any_cwd(tmp_path, monkeypatch):
    # 回退 CID 字体/去掉粗体映射都会让实际 PDF 的 FontFile2 断言失败。
    monkeypatch.chdir(tmp_path)
    output = tmp_path / "report.pdf"
    PDFGenerator().generate_report({
        "title": "仪器测试报告 LTE/NR 2×2",
        "report_type": "single_execution",
        "step_results": [{"name": "冻结请求", "parameters": {
            "基站功率": "−85 dBm，未确认", "频率": "3500 MHz", "来源": "系统默认",
        }}],
    }, None, str(output))
    reader = PdfReader(output)
    descriptors = []
    for page in reader.pages:
        for font in page["/Resources"]["/Font"].values():
            descriptor = font.get_object().get("/FontDescriptor")
            if descriptor:
                descriptors.append(descriptor.get_object())
    embedded = [d for d in descriptors if "/FontFile2" in d]
    assert len({str(d["/FontName"]) for d in embedded}) >= 2
    assert any("Bold" in str(d["/FontName"]) for d in embedded)
    text = "\n".join(page.extract_text() for page in reader.pages)
    assert "仪器测试报告" in text
    assert "系统默认" in text
    assert "−85 dBm" in text


@pytest.mark.parametrize("section,data", [
    ("vrt_phases", {"phases": [{"name": "验证", "status": "failed", "duration_s": 1, "pass_rate": None}]}),
    ("vrt_kpi_summary", {"kpi_summary": [{"name": "吞吐", "mean": 1, "min": 1, "max": 1, "passed": False}]}),
])
def test_failed_marker_is_readable_in_embedded_font(tmp_path, section, data):
    output = tmp_path / "failed.pdf"
    PDFGenerator().generate_report(data, {"sections": [{"type": section, "title": "结果"}]}, str(output))
    text = "\n".join(p.extract_text() for p in PdfReader(output).pages)
    assert "\x00" not in text
    assert "failed" in text or "FAIL" in text
