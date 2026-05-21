from medcheck.core.context import ClinicalContext, DicomSeries, PatientInfo, PipelineContext


def test_pipeline_context_creation():
    ctx = PipelineContext()
    assert ctx.dicom_series == []
    assert ctx.clinical_context is None
    assert ctx.detected_anatomy is None


def test_clinical_context():
    cc = ClinicalContext(
        symptoms="Medial knee pain",
        trauma="Valgus stress",
        trauma_date="2026-05-11",
        suspected_diagnosis="MCL tear",
        patient_age=29,
        patient_sex="M",
        anatomy="knee",
    )
    assert cc.symptoms == "Medial knee pain"
    assert cc.anatomy == "knee"


def test_patient_info_defaults():
    p = PatientInfo()
    assert p.name == ""
    assert p.sex == ""


def test_dicom_series():
    s = DicomSeries(description="pd_tse_fs_sag", series_number=2, modality="MR")
    assert s.description == "pd_tse_fs_sag"
    assert s.slices == []
