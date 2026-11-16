"""Read the same listings for ATS and manual input without eligibility inference."""
from urllib.parse import urlsplit
from sqlalchemy import case, func, or_, select, true
from app.models.core import JobListing, JobSource
from app.api.schemas import JobDetail, JobPage, JobSummary, SourceOption

# Literal mentions in location text only. Negation is intentionally not interpreted.
REMOTE_PATTERN = r"\m(remote|telecommut(e|ing)|work[ -]from[ -]home)\M|원격|재택"


def safe_source_url(value):
    if not value or any(character.isspace() or ord(character) < 32 for character in value) or "\\" in value:
        return None
    try:
        parsed = urlsplit(value)
        if parsed.scheme.lower() not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
            return None
        parsed.port
    except ValueError:
        return None
    return value


def remote_expression():
    return case(
        (or_(JobListing.location_text.is_(None), JobListing.location_text.op("~")(r"^[[:space:]]*$")), "UNKNOWN"),
        (JobListing.location_text.op("~*")(REMOTE_PATTERN), "PRESENT"),
        else_="NOT_MENTIONED")


def literal_match(column, value):
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return column.ilike(f"%{escaped}%", escape="\\")


def public_job(job, mention, *, detail=False):
    fields = {name: getattr(job, name) for name in JobSummary.model_fields
              if name not in ("origin", "remote_mention", "source_url")}
    fields.update(origin="manual" if job.source_id is None else "ats", remote_mention=mention,
                  source_url=safe_source_url(job.source_url))
    if detail:
        return JobDetail(**fields, raw_text=job.raw_text, description_text=job.description_text,
                         source_updated_at=job.source_updated_at)
    return JobSummary(**fields)


def get_job(db, job_id):
    row = db.execute(select(JobListing, remote_expression()).where(JobListing.id == job_id)).first()
    return public_job(*row, detail=True) if row else None


def list_jobs(db, *, page, page_size, q=None, location=None, country_text=None, region_text=None,
              source_id=None, origin=None, remote_mention=None, sort="created_desc"):
    filters = []
    if q:
        filters.append(or_(*(literal_match(column, q) for column in (
            JobListing.title, JobListing.company_name, JobListing.location_text,
            func.coalesce(JobListing.description_text, JobListing.raw_text)))))
    for value in (location, country_text, region_text):
        if value:
            filters.append(literal_match(JobListing.location_text, value))
    if source_id:
        filters.append(JobListing.source_id == source_id)
    if origin:
        filters.append(JobListing.source_id.is_(None) if origin == "manual" else JobListing.source_id.is_not(None))
    if remote_mention:
        filters.append(remote_expression() == remote_mention)
    # Count and rows share a statement snapshot even while ingestion is running.
    total_query = select(func.count()).select_from(JobListing).where(*filters).cte("total")
    sort_column = {"created_desc": JobListing.created_at, "published_desc": JobListing.published_at,
                   "updated_desc": JobListing.updated_at}[sort]
    page_query = select(JobListing.id).where(*filters).order_by(
        sort_column.desc().nulls_last(), JobListing.id.desc()).offset((page - 1) * page_size).limit(page_size).cte("page")
    rows = db.execute(select(total_query.c.count, JobListing, remote_expression()).select_from(total_query)
                      .outerjoin(page_query, true()).outerjoin(JobListing, JobListing.id == page_query.c.id)
                      .order_by(sort_column.desc().nulls_last(), JobListing.id.desc())).all()
    total = rows[0][0]
    sources = db.scalars(select(JobSource).where(select(JobListing.id).where(
        JobListing.source_id == JobSource.id).exists()).order_by(JobSource.company_name, JobSource.id)).all()
    return JobPage(items=[public_job(job, mention) for _, job, mention in rows if job is not None],
                   page=page, page_size=page_size, total=total, total_pages=(total + page_size - 1) // page_size,
                   source_options=[SourceOption(id=source.id, provider=source.provider,
                                   company_name=source.company_name, board_token=source.board_token) for source in sources])
