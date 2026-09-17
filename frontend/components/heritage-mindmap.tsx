"use client";

import { useId, useMemo, useState, type CSSProperties } from "react";
import { formatCategory } from "@/lib/format";
import type { LearningMindmap, LearningTimelineEntry } from "@/lib/api";
import type { Artifact, ArtifactStory } from "@/lib/types";

interface HeritageMindmapProps {
  artifact: Artifact;
  story: ArtifactStory;
  learningMindmap?: LearningMindmap | null;
  timeline?: LearningTimelineEntry[];
}

interface MindmapBranch {
  id: string;
  label: string;
  relation: string;
  items: MindmapItem[];
  evidence: string;
  tone: MindmapTone;
}

interface MindmapItem {
  label: string;
  note: string | null;
}

type MindmapTone = "history" | "identity" | "meaning" | "evidence";

const ZOOM_LEVELS = [0.9, 1, 1.15] as const;
const RELATION_LABELS: Record<LearningMindmap["branches"][number]["relation"], string> = {
  identified_by: "được nhận diện qua",
  dated_to: "được ghi vào",
  located_at: "được lưu giữ tại",
  associated_with: "được liên hệ với",
  used_by: "được sử dụng bởi",
  part_of: "là một phần của",
  led_to: "dẫn đến",
  evidenced_by: "được minh chứng bởi",
  described_by: "được mô tả bởi",
};

export function HeritageMindmap({ artifact, story, learningMindmap, timeline = [] }: HeritageMindmapProps) {
  const baseId = useId();
  const branches = useMemo(
    () => learningMindmap ? buildLearningBranches(learningMindmap) : buildBranches(artifact, story),
    [artifact, learningMindmap, story],
  );
  const [collapsed, setCollapsed] = useState<Set<string>>(() => new Set());
  const [zoomIndex, setZoomIndex] = useState(1);
  const zoom = ZOOM_LEVELS[zoomIndex];
  const historicalFlow = useMemo(
    () => buildHistoricalFlow(timeline, branches),
    [branches, timeline],
  );
  const knowledgePointCount = branches.reduce((total, branchValue) => total + branchValue.items.length, 0);

  function toggleBranch(id: string) {
    setCollapsed((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  return (
    <section className="mindmap" aria-labelledby={`${baseId}-title`}>
      <div className="mindmap-heading">
        <div>
          <span className="mindmap-kicker">Mindmap tương tác</span>
          <h4 id={`${baseId}-title`}>Sơ đồ luồng lịch sử và mối liên hệ</h4>
          <p>Đi từ bối cảnh, qua diễn biến đến ý nghĩa của hiện vật; mở từng nhánh để xem nội dung chi tiết.</p>
        </div>
        <div className="mindmap-controls" aria-label="Điều khiển sơ đồ kiến thức">
          <button
            type="button"
            onClick={() => setZoomIndex((value) => Math.max(0, value - 1))}
            disabled={zoomIndex === 0}
            aria-label="Thu nhỏ sơ đồ"
          >
            −
          </button>
          <output aria-live="polite" aria-label="Mức phóng sơ đồ">
            {Math.round(zoom * 100)}%
          </output>
          <button
            type="button"
            onClick={() => setZoomIndex((value) => Math.min(ZOOM_LEVELS.length - 1, value + 1))}
            disabled={zoomIndex === ZOOM_LEVELS.length - 1}
            aria-label="Phóng to sơ đồ"
          >
            +
          </button>
          <button type="button" onClick={() => setZoomIndex(1)}>
            Đặt lại
          </button>
        </div>
      </div>

      <div
        className="mindmap-viewport"
        data-zoom={zoom}
        style={{ "--mindmap-scale": zoom } as CSSProperties}
      >
        <div className="mindmap-center">
          <span className="mindmap-center-orbit" aria-hidden="true" />
          <span>Điểm neo câu chuyện</span>
          <strong>{learningMindmap?.central_label || artifact.name}</strong>
          <small>{branches.length} mối liên hệ · {knowledgePointCount} điểm kiến thức</small>
        </div>

        {historicalFlow.length > 0 && (
          <section className="mindmap-history" aria-labelledby={`${baseId}-history-title`}>
            <div className="mindmap-section-heading">
              <span>01 · Dòng diễn tiến</span>
              <h5 id={`${baseId}-history-title`}>Luồng lịch sử liên quan đến hiện vật</h5>
              <p>Các mốc được sắp xếp theo trình tự để thấy hiện vật xuất hiện trong bối cảnh nào và dẫn tới điều gì.</p>
            </div>
            <ol className="mindmap-history-flow" aria-label="Các mốc lịch sử theo trình tự">
              {historicalFlow.map((entry, index) => (
                <li key={entry.id}>
                  <span className="mindmap-history-stage">Mốc {String(index + 1).padStart(2, "0")}</span>
                  <span className="mindmap-history-index" aria-hidden="true">{index + 1}</span>
                  <div className="mindmap-history-card">
                    {entry.time && <time>{entry.time}</time>}
                    <strong>{entry.label}</strong>
                  </div>
                  {index < historicalFlow.length - 1 && (
                    <span className="mindmap-flow-arrow" aria-hidden="true">→</span>
                  )}
                </li>
              ))}
            </ol>
          </section>
        )}

        {branches.length > 0 ? (
          <section className="mindmap-relations" aria-labelledby={`${baseId}-relations-title`}>
            <div className="mindmap-section-heading">
              <span>02 · Mở rộng kiến thức</span>
              <h5 id={`${baseId}-relations-title`}>Các mối liên hệ quanh hiện vật</h5>
              <p>Mỗi cụm giải thích một lát cắt: nhận diện, bối cảnh, câu chuyện, ý nghĩa hoặc căn cứ dữ liệu.</p>
            </div>
            <ul className="mindmap-tree" aria-label={`Kiến thức về ${artifact.name}`}>
              {branches.map((branch, index) => {
                const contentId = `${baseId}-${branch.id}`;
                const expanded = !collapsed.has(branch.id);
                return (
                  <li className={`mindmap-branch mindmap-tone-${branch.tone}`} key={branch.id}>
                    <button
                      type="button"
                      className="mindmap-branch-toggle"
                      aria-expanded={expanded}
                      aria-controls={contentId}
                      onClick={() => toggleBranch(branch.id)}
                    >
                      <span className="mindmap-branch-number" aria-hidden="true">
                        {String(index + 1).padStart(2, "0")}
                      </span>
                      <span className="mindmap-branch-title">
                        <strong>{branch.label}</strong>
                        <small className="mindmap-relation">Hiện vật {branch.relation}</small>
                      </span>
                      <span className="mindmap-branch-chevron" aria-hidden="true">{expanded ? "−" : "+"}</span>
                    </button>
                    <div className="mindmap-branch-content" id={contentId} hidden={!expanded}>
                      <ul className="mindmap-node-list">
                        {branch.items.map((item) => (
                          <li key={`${item.label}-${item.note || ""}`}>
                            <span className="mindmap-node-dot" aria-hidden="true" />
                            <div>
                              <strong>{item.label}</strong>
                              {item.note && <p>{item.note}</p>}
                            </div>
                          </li>
                        ))}
                      </ul>
                      {branch.evidence && (
                        <small className="mindmap-evidence">Căn cứ dữ liệu: {branch.evidence}</small>
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>
          </section>
        ) : (
          <p className="mindmap-empty">
            Chưa đủ dữ liệu để tạo thêm nhánh kiến thức cho hiện vật này.
          </p>
        )}
      </div>
    </section>
  );
}

function buildLearningBranches(mindmap: LearningMindmap): MindmapBranch[] {
  return mindmap.branches
    .map((branchValue) => ({
      id: branchValue.id,
      label: branchValue.label,
      relation: RELATION_LABELS[branchValue.relation] || "được mô tả bởi",
      items: uniqueItems(branchValue.nodes.map((node) => ({
        label: node.label,
        note: node.note,
      }))),
      evidence: unique([
        ...(branchValue.evidence_refs || []),
        ...branchValue.nodes.flatMap((node) => node.evidence_refs),
      ]).join(", "),
      tone: branchTone(branchValue.id, branchValue.relation),
    }))
    .filter((branchValue) => branchValue.items.length > 0);
}

function buildBranches(artifact: Artifact, story: ArtifactStory): MindmapBranch[] {
  const branches: Array<MindmapBranch | null> = [];
  const images = story.deep.images.length ? story.deep.images : artifact.images;
  const views = unique(images.map((image) => image.view).filter(isText));

  branches.push(
    branch(
      "identity",
      "Nhận diện",
      "được nhận diện qua",
      [formatCategory(artifact.category), ...views.map((view) => `Góc nhìn: ${view}`)],
      "category, images[].view",
    ),
  );

  const timeItems: string[] = [];
  const period = artifact.historical_period || artifact.period || story.quick.period;
  const year = artifact.year ?? story.quick.year;
  if (period) timeItems.push(period);
  if (year != null) timeItems.push(`Năm được ghi nhận: ${year}`);
  branches.push(
    branch("time", "Thời gian", "được ghi vào", timeItems, "historical_period, year"),
  );

  const location = artifact.location;
  branches.push(
    branch(
      "place",
      "Địa điểm",
      "được lưu giữ tại",
      unique(
        [location?.address, location?.city, location?.province, location?.country].filter(isText),
      ),
      "location",
    ),
  );

  branches.push(
    branch(
      "context",
      "Bối cảnh lịch sử",
      "được liên hệ với",
      unique([story.overview.context, story.deep.event, artifact.event].filter(isText)),
      "overview.context, historical_info.event",
    ),
  );
  branches.push(
    branch(
      "role",
      "Vai trò và công dụng",
      "được mô tả bởi",
      unique([story.overview.what_it_is, story.overview.role].filter(isText)),
      "overview.what_it_is, overview.role",
    ),
  );
  branches.push(
    branch(
      "meaning",
      "Ý nghĩa",
      "được mô tả bởi",
      unique([story.overview.significance].filter(isText)),
      "overview.significance",
    ),
  );
  branches.push(
    branch(
      "story",
      "Câu chuyện",
      "được mô tả bởi",
      unique(
        [story.overview.description, ...(story.overview.paragraphs || [])]
          .filter(isText)
          .map((text) => shorten(text, 150)),
      ),
      "overview.description, overview.paragraphs",
    ),
  );
  branches.push(
    branch(
      "events",
      "Sự kiện liên quan",
      "được liên hệ với",
      unique((story.deep.related_events || []).filter(isText)),
      "deep.related_events",
    ),
  );
  branches.push(
    branch(
      "people",
      "Nhân vật liên quan",
      "được liên hệ với",
      unique((story.deep.people || []).filter(isText)),
      "deep.people",
    ),
  );
  branches.push(
    branch(
      "keywords",
      "Từ khóa cần nhớ",
      "được mô tả bởi",
      unique(artifact.tags.filter(isText)),
      "tags",
    ),
  );

  const source = story.deep.source || artifact.source;
  branches.push(
    branch(
      "source",
      "Nguồn kiểm chứng",
      "được minh chứng bởi",
      source ? [shorten(source, 180)] : [],
      "source",
    ),
  );

  return branches.filter((entry): entry is MindmapBranch => entry !== null);
}

function branch(
  id: string,
  label: string,
  relation: string,
  values: string[],
  evidence: string,
): MindmapBranch | null {
  const items = uniqueItems(values.map((value) => ({
    label: shorten(value, 180),
    note: null,
  })));
  return items.length
    ? { id, label, relation, items, evidence, tone: branchTone(id) }
    : null;
}

interface HistoricalFlowEntry {
  id: string;
  time: string | null;
  label: string;
}

function buildHistoricalFlow(
  timeline: LearningTimelineEntry[],
  branches: MindmapBranch[],
): HistoricalFlowEntry[] {
  const chronological = timeline.map((entry, index) => ({
    id: `timeline-${index}-${entry.year ?? entry.period ?? "period"}`,
    time: entry.year !== null ? String(entry.year) : entry.period,
    label: entry.label,
  }));
  if (chronological.length > 0) return chronological;

  const historicalBranchIds = new Set(["time", "context", "events", "history", "consequence"]);
  return branches
    .filter((entry) => historicalBranchIds.has(entry.id.toLocaleLowerCase("vi-VN")))
    .flatMap((entry) => entry.items.map((item, index) => ({
      id: `${entry.id}-${index}`,
      time: index === 0 ? entry.label : null,
      label: item.note ? `${item.label} — ${item.note}` : item.label,
    })));
}

function branchTone(
  id: string,
  relation?: LearningMindmap["branches"][number]["relation"],
): MindmapTone {
  const normalized = id.toLocaleLowerCase("vi-VN");
  if (
    relation === "evidenced_by"
    || ["source", "evidence", "reference", "nguon"].some((token) => normalized.includes(token))
  ) return "evidence";
  if (
    relation === "dated_to"
    || relation === "led_to"
    || ["time", "history", "context", "event", "consequence", "timeline"].some((token) => normalized.includes(token))
  ) return "history";
  if (
    ["meaning", "significance", "legacy", "story", "impact"].some((token) => normalized.includes(token))
  ) return "meaning";
  return "identity";
}

function uniqueItems(values: MindmapItem[]): MindmapItem[] {
  const seen = new Set<string>();
  return values.reduce<MindmapItem[]>((items, item) => {
    const label = item.label.trim();
    const note = item.note?.trim() || null;
    if (!label) return items;
    const key = `${label}\u0000${note || ""}`;
    if (seen.has(key)) return items;
    seen.add(key);
    items.push({ label, note });
    return items;
  }, []);
}

function unique(values: string[]): string[] {
  return Array.from(new Set(values.map((value) => value.trim()).filter(Boolean)));
}

function isText(value: string | null | undefined): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function shorten(value: string, maxLength: number): string {
  const normalized = value.replace(/\s+/g, " ").trim();
  if (normalized.length <= maxLength) return normalized;
  const clipped = normalized.slice(0, maxLength - 1);
  const boundary = clipped.lastIndexOf(" ");
  return `${clipped.slice(0, Math.max(boundary, maxLength * 0.7))}…`;
}
