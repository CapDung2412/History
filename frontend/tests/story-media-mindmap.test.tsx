import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { StoryExplorer } from "@/components/story-explorer";
import type { Artifact, ArtifactStory } from "@/lib/types";
import { artifact, story } from "./fixtures";

const requestLearningContentMock = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, requestLearningContent: requestLearningContentMock };
});

beforeEach(() => {
  requestLearningContentMock.mockReset();
  requestLearningContentMock.mockImplementation(() => new Promise(() => undefined));
});

describe("story media and grounded exploration", () => {
  it("opens one accessible lightbox and restores focus after Escape", async () => {
    const user = userEvent.setup();
    render(<StoryExplorer artifact={artifact} story={story} />);

    const trigger = screen.getByRole("button", { name: /Xem ảnh lớn: Ảnh kiểm thử/ });
    const thumbnail = within(trigger).getByRole("img");
    expect(thumbnail).toHaveAttribute("loading", "eager");
    expect(thumbnail).toHaveAttribute("decoding", "async");
    expect(thumbnail.getAttribute("src")).toContain("width=960");

    trigger.focus();
    await user.click(trigger);
    const dialog = screen.getByRole("dialog", { name: "Xem ảnh hiện vật" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(document.querySelectorAll(".image-lightbox")).toHaveLength(1);
    expect(document.body.style.overflow).toBe("hidden");
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Đóng ảnh phóng lớn" })).toHaveFocus(),
    );

    fireEvent.load(within(dialog).getByAltText("Ảnh kiểm thử"));
    await user.keyboard("{Escape}");
    await waitFor(() => expect(dialog).not.toHaveAttribute("open"));
    expect(document.body.style.overflow).toBe("");
    expect(trigger).toHaveFocus();

    await user.click(trigger);
    await user.click(screen.getByRole("button", { name: "Đóng ảnh phóng lớn" }));
    await waitFor(() => expect(dialog).not.toHaveAttribute("open"));
    expect(trigger).toHaveFocus();
  });

  it("shows grounded images in the one-minute story and closes on the backdrop", async () => {
    const user = userEvent.setup();
    render(<StoryExplorer artifact={artifact} story={story} />);
    await user.click(screen.getByRole("tab", { name: /Câu chuyện/ }));

    const gallery = screen.getByLabelText("Ảnh liên quan đến câu chuyện một phút");
    const trigger = within(gallery).getByRole("button", { name: /Xem ảnh lớn/ });
    const thumbnail = within(trigger).getByRole("img");
    expect(thumbnail).toHaveAttribute("loading", "lazy");
    expect(thumbnail).toHaveAttribute("srcset");
    expect(thumbnail.getAttribute("src")).toContain("width=640");

    await user.click(trigger);
    const dialog = screen.getByRole("dialog", { name: "Xem ảnh hiện vật" });
    fireEvent.click(dialog);
    await waitFor(() => expect(dialog).not.toHaveAttribute("open"));
  });

  it("builds only data-backed timeline and mindmap branches", async () => {
    const user = userEvent.setup();
    const enrichedArtifact: Artifact = {
      ...artifact,
      historical_period: "Kháng chiến chống Mỹ",
      year: 1975,
      tags: ["bản đồ", "tư liệu"],
      location: { city: "Thành phố Hồ Chí Minh" },
      source: null,
      source_verified: false,
      images: [{ ...artifact.images[0], year: 1974, view: "chính diện" }],
    };
    const enrichedStory: ArtifactStory = {
      ...story,
      quick: { ...story.quick, year: 1975, period: "Kháng chiến chống Mỹ" },
      overview: {
        ...story.overview,
        context: "Bối cảnh được ghi trong dữ liệu kiểm thử.",
      },
      deep: {
        ...story.deep,
        event: "Sự kiện được ghi trong dữ liệu kiểm thử",
        related_events: ["Sự kiện được ghi trong dữ liệu kiểm thử"],
        people: ["Nhân vật kiểm thử"],
        images: [{ ...artifact.images[0], year: 1974, view: "chính diện" }],
        source: null,
        source_verified: false,
      },
    };

    render(<StoryExplorer artifact={enrichedArtifact} story={enrichedStory} />);
    await user.click(screen.getByRole("tab", { name: /Khám phá sâu/ }));

    expect(screen.getAllByText("1974").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("1975").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Chưa có nguồn kiểm chứng trong bộ dữ liệu.")).toBeInTheDocument();

    const mindmapDetails = screen.getByText("Sơ đồ diễn biến lịch sử").closest("details");
    expect(mindmapDetails).toHaveAttribute("open");
    expect(screen.getByRole("heading", { name: "Luồng lịch sử liên quan đến hiện vật" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Các mối liên hệ quanh hiện vật" })).toBeInTheDocument();
    expect(screen.getByText(/\d+ mối liên hệ · \d+ chi tiết lịch sử/)).toBeInTheDocument();
    expect(screen.getAllByText(/Mốc 0\d/).length).toBeGreaterThanOrEqual(2);
    const identity = screen.getByRole("button", { name: /Nhận diện/ });
    expect(identity).toHaveAttribute("aria-expanded", "true");
    expect(identity).toHaveTextContent("được nhận diện qua");
    await user.click(identity);
    expect(identity).toHaveAttribute("aria-expanded", "false");

    expect(screen.getByRole("status", { name: "Mức phóng sơ đồ" })).toHaveTextContent("100%");
    await user.click(screen.getByRole("button", { name: "Phóng to sơ đồ" }));
    expect(screen.getByRole("status", { name: "Mức phóng sơ đồ" })).toHaveTextContent("115%");
    await user.click(screen.getByRole("button", { name: "Đặt lại" }));
    expect(screen.getByRole("status", { name: "Mức phóng sơ đồ" })).toHaveTextContent("100%");
  });

  it("replaces a failed thumbnail with a readable caption", () => {
    render(<StoryExplorer artifact={artifact} story={story} />);
    fireEvent.error(screen.getByAltText("Ảnh kiểm thử"));
    expect(screen.getByText("Chưa tải được ảnh")).toBeInTheDocument();
    expect(screen.getByText("Ảnh kiểm thử")).toBeInTheDocument();
  });

  it("loads grounded deep content once and labels missing-source fallback honestly", async () => {
    const user = userEvent.setup();
    requestLearningContentMock.mockResolvedValue({
      artifact_id: artifact.item_id,
      data_status: "missing",
      source_status: "missing",
      generation_status: "fallback_missing_source",
      cache_status: "bypass",
      model: null,
      notice: "Hiện vật chưa có đủ nguồn kiểm chứng để tạo phần khám phá sâu. Hệ thống không gọi AI sinh nội dung.",
      references: [],
      content: {
        factual_claims: [],
        storytelling: {
          quick: { text: artifact.name, claim_ids: [] },
          one_minute: { text: artifact.description, claim_ids: [] },
        },
        deep_sections: [],
        timeline: [
          { year: 1961, period: null, label: "Bối cảnh lịch sử mở đầu" },
          { year: 1975, period: null, label: "Dấu mốc kết thúc mạch sự kiện" },
        ],
        keywords: [],
        related_videos: [],
        mindmap: {
          central_label: artifact.name,
          branches: [{
            id: "identity",
            label: "Nhận diện từ máy chủ",
            relation: "identified_by",
            evidence_refs: ["artifact.name"],
            nodes: [{
              id: "name",
              label: artifact.name,
              note: "Tên trong JSON",
              evidence_refs: ["artifact.name"],
            }],
          }],
        },
      },
    });
    render(<StoryExplorer artifact={artifact} story={story} />);

    await user.click(screen.getByRole("tab", { name: /Khám phá sâu/ }));
    expect(await screen.findByText("Dữ liệu hiện vật đang thiếu nguồn kiểm chứng")).toBeInTheDocument();
    expect(screen.getByText(/không gọi AI sinh nội dung/)).toBeInTheDocument();
    expect(screen.getByText("Sơ đồ diễn biến lịch sử").closest("details")).toHaveAttribute("open");
    expect(screen.getByRole("button", { name: /Nhận diện từ máy chủ/ })).toBeInTheDocument();
    expect(screen.queryByText("Video YouTube liên quan")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /YouTube/i })).not.toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: /Nhìn nhanh/ }));
    await user.click(screen.getByRole("tab", { name: /Khám phá sâu/ }));
    expect(requestLearningContentMock).toHaveBeenCalledTimes(1);
  });

  it("shows a distinct generated one-minute story and evidence for deep sections", async () => {
    const user = userEvent.setup();
    const oneMinute =
      "Bản kể một phút dùng dữ kiện đã kiểm chứng và khác với thẻ nhận diện nhanh.";
    requestLearningContentMock.mockResolvedValue({
      artifact_id: artifact.item_id,
      data_status: "sufficient",
      source_status: "verified",
      generation_status: "generated",
      cache_status: "miss",
      model: "test-model",
      notice: "Nội dung có tham chiếu.",
      references: [
        {
          ref: "history.description",
          label: "Mô tả dữ liệu",
          value: artifact.description,
          source_status: "verified",
          url: "https://example.test/source",
        },
        {
          ref: "web.2",
          label: "Nguồn trùng cần loại bỏ",
          value: "Cùng một địa chỉ nguồn.",
          source_status: "available_unverified",
          url: "https://example.test/source#duplicate",
        },
        {
          ref: "web.3",
          label: "Video tư liệu từ kênh chính thức",
          value: "Trang video cụ thể do công cụ tìm kiếm trả về.",
          source_status: "verified",
          url: "https://www.youtube.com/watch?v=AbCdEfGhI12",
        },
      ],
      content: {
        factual_claims: [{
          id: "fact-description",
          text: artifact.description,
          evidence_refs: ["history.description"],
        }],
        storytelling: {
          quick: { text: artifact.name, claim_ids: ["fact-description"] },
          one_minute: { text: oneMinute, claim_ids: ["fact-description"] },
        },
        deep_sections: [
          {
            key: "overview",
            title: "Giới thiệu tổng quát",
            summary: "Khái quát riêng của phần khám phá sâu",
            body: "Hiện vật gắn trực tiếp với một chuỗi diễn biến lịch sử có nguồn xác nhận.",
            claim_ids: ["fact-description"],
          },
          {
            key: "context",
            title: "Bối cảnh lịch sử cụ thể",
            summary: "Tóm tắt có dữ kiện",
            body: artifact.description,
            claim_ids: ["fact-description"],
          },
        ],
        timeline: [
          { year: 1961, period: null, label: "Bối cảnh lịch sử mở đầu" },
          { year: 1975, period: null, label: "Dấu mốc kết thúc mạch sự kiện" },
        ],
        keywords: [],
        related_videos: [{
          title: "Phim tư liệu về hiện vật",
          url: "https://www.youtube.com/watch?v=AbCdEfGhI12",
          channel_name: "Đài truyền hình kiểm thử",
          trust_level: "official",
          trust_reason: "Đây là kênh chính thức của cơ quan truyền hình kiểm thử.",
          relevance: "Trình bày bối cảnh lịch sử liên quan.",
          scope: "related_event",
          evidence_refs: ["web.3"],
        }],
        mindmap: {
          central_label: artifact.name,
          branches: [{
            id: "context",
            label: "Bối cảnh",
            relation: "described_by",
            evidence_refs: ["history.description"],
            nodes: [{
              id: "description",
              label: artifact.description,
              note: null,
              evidence_refs: ["history.description"],
            }, ...Array.from({ length: 5 }, (_, index) => ({
              id: `detail-${index + 2}`,
              label: `Chi tiết lịch sử ${index + 2}`,
              note: `Giải thích ${index + 2}`,
              evidence_refs: ["history.description"],
            }))],
          }],
        },
      },
    });
    render(<StoryExplorer artifact={artifact} story={story} />);

    await user.click(screen.getByRole("tab", { name: /Khám phá sâu/ }));
    expect(
      await screen.findByText("Sự kiện và địa điểm gắn với hiện vật"),
    ).toBeInTheDocument();
    expect(screen.getByText("Giới thiệu tổng quát")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: artifact.name })).toBeInTheDocument();
    expect(screen.getByText("Khái quát riêng của phần khám phá sâu")).toBeInTheDocument();
    expect(screen.getByText("Hiện vật gắn trực tiếp với một chuỗi diễn biến lịch sử có nguồn xác nhận.")).toBeInTheDocument();
    expect(screen.queryByText(oneMinute)).not.toBeInTheDocument();
    expect(screen.getAllByText("Căn cứ dữ liệu").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByRole("link", { name: "Mở nguồn" })[0]).toHaveAttribute(
      "href",
      "https://example.test/source",
    );
    await user.click(screen.getByText("Nguồn tham khảo"));
    expect(screen.getByRole("link", { name: "Mô tả dữ liệu" })).toHaveAttribute(
      "href",
      "https://example.test/source",
    );
    expect(screen.queryByRole("link", { name: "Nguồn trùng cần loại bỏ" })).not.toBeInTheDocument();
    expect(screen.getByText(/nguồn do AI tìm trên web cần được đối chiếu/i)).toBeInTheDocument();

    expect(screen.getByText("Sơ đồ diễn biến lịch sử").closest("details")).toHaveAttribute("open");
    const flowHeading = screen.getByRole("heading", { name: "Luồng lịch sử liên quan đến hiện vật" });
    expect(flowHeading).toBeInTheDocument();
    const flow = flowHeading.closest("section");
    expect(flow).not.toBeNull();
    expect(within(flow as HTMLElement).getByText("Bối cảnh lịch sử mở đầu")).toBeInTheDocument();
    expect(within(flow as HTMLElement).getByText("Dấu mốc kết thúc mạch sự kiện")).toBeInTheDocument();
    expect(screen.getByText("Chi tiết lịch sử 6")).toBeInTheDocument();
    expect(screen.getByText("Giải thích 6")).toBeInTheDocument();
    expect(screen.queryByText("Video YouTube liên quan")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Phim tư liệu về hiện vật/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Video tư liệu từ kênh chính thức" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: /Câu chuyện/ }));
    const oneMinuteCopies = screen.getAllByText(oneMinute);
    expect(oneMinuteCopies.length).toBeGreaterThanOrEqual(2);
    expect(oneMinuteCopies[0]).not.toHaveTextContent(artifact.name);
    const caption = screen.getByText("Phụ đề").closest(".tts-caption");
    expect(caption).not.toBeNull();
    expect(within(caption as HTMLElement).getByText(oneMinute)).toBeInTheDocument();
    expect(screen.getByText(/AI biên soạn từ dữ liệu tham chiếu/)).toBeInTheDocument();
  });
});
