const result = document.getElementById("result");
const recommendationsContainer = document.getElementById("recommendations");
const recommendationHelper = document.getElementById("recommendationHelper");
let selectedRecommendationIndex = null;
let latestRecommendations = [];

async function getActiveTab() {
  const [tab] = await chrome.tabs.query({
    active: true,
    currentWindow: true
  });

  return tab;
}

async function sendToContent(message) {
  const tab = await getActiveTab();

  return new Promise((resolve) => {
    chrome.tabs.sendMessage(tab.id, message, (response) => {
      if (chrome.runtime.lastError) {
        const errorResponse = {
          ok: false,
          warning: chrome.runtime.lastError.message
        };

        result.textContent = JSON.stringify(
          errorResponse,
          null,
          2
        );
        resolve(errorResponse);
        return;
      }

      result.textContent = JSON.stringify(
        response,
        null,
        2
      );
      resolve(response);
    });
  });
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function buildSignalBadges(hotel) {
  const badges = [];

  if (hotel.signals?.reviewTier === "excellent") {
    badges.push("평점 매우 높음");
  } else if (hotel.signals?.reviewTier === "strong") {
    badges.push("평점 높음");
  } else if (hotel.signals?.reviewTier === "good") {
    badges.push("평점 양호");
  }

  if (hotel.signals?.luxuryTier === "strong") {
    badges.push("럭셔리 강함");
  } else if (hotel.signals?.luxuryTier === "good") {
    badges.push("고급 숙소");
  }

  if (hotel.signals?.valueBucket === "strong") {
    badges.push("가성비 매우 좋음");
  } else if (hotel.signals?.valueBucket === "good") {
    badges.push("가성비 좋음");
  } else if (hotel.signals?.valueBucket === "moderate") {
    badges.push("가성비 무난");
  }

  if (hotel.signals?.hasBreakfast) {
    badges.push("조식");
  }

  if (hotel.signals?.hasMetroAccess) {
    badges.push("지하철");
  }

  if (hotel.signals?.eiffelDistanceKm !== null && hotel.signals?.eiffelDistanceKm !== undefined) {
    badges.push(`에펠탑 ${hotel.signals.eiffelDistanceKm}km`);
  } else if (hotel.signals?.mentionsEiffel) {
    badges.push("에펠탑 언급");
  }

  return badges;
}

function renderRecommendations(recommendations = []) {
  latestRecommendations = recommendations;

  if (!recommendations.length) {
    recommendationsContainer.innerHTML = "";
    recommendationHelper.textContent =
      "추천 결과가 아직 없습니다. 검색 결과 페이지에서 추천을 실행해 주세요.";
    return;
  }

  if (
    selectedRecommendationIndex === null ||
    !recommendations.some((hotel) => hotel.index === selectedRecommendationIndex)
  ) {
    selectedRecommendationIndex = recommendations[0].index;
  }

  recommendationsContainer.innerHTML = recommendations
    .map((hotel, position) => {
      const reasons = hotel.reasons?.length
        ? hotel.reasons.join(" | ")
        : "추천 이유 없음";
      const signalBadges = buildSignalBadges(hotel);

      const isSelected = hotel.index === selectedRecommendationIndex;

      return `
        <div class="recommendation-card ${isSelected ? "selected" : ""}">
          <div class="recommendation-rank">TOP ${position + 1}</div>
          <div class="recommendation-name">${escapeHtml(hotel.name || "Unknown hotel")}</div>
          <div class="recommendation-meta">
            Score ${escapeHtml(hotel.rankingScore)} · Review ${escapeHtml(hotel.scoreText || "-")}
          </div>
          <div class="recommendation-meta">${escapeHtml(hotel.price || "가격 정보 없음")}</div>
          <div class="recommendation-signals">
            ${signalBadges.length
              ? signalBadges.map((badge) => `<span class="signal-badge">${escapeHtml(badge)}</span>`).join("")
              : '<span class="signal-badge">추가 신호 없음</span>'}
          </div>
          <div class="recommendation-reasons">${escapeHtml(reasons)}</div>
          <button data-hotel-index="${hotel.index}">
            ${isSelected ? "Selected" : "Select This Hotel"}
          </button>
        </div>
      `;
    })
    .join("");

  recommendationHelper.textContent =
    "후보를 선택한 뒤 Confirm Selected Hotel을 누르면 해당 호텔 페이지로 이동합니다.";

  recommendationsContainer
    .querySelectorAll("button[data-hotel-index]")
    .forEach((button) => {
      button.addEventListener("click", () => {
        selectedRecommendationIndex = Number(button.dataset.hotelIndex);
        renderRecommendations(latestRecommendations);
      });
    });
}

function getPayloadFromTextarea() {
  const raw = document.getElementById(
    "payloadTextarea"
  ).value;

  try {
    return JSON.parse(raw);
  } catch (error) {
    result.textContent = JSON.stringify(
      {
        ok: false,
        error: "Invalid JSON payload"
      },
      null,
      2
    );

    return null;
  }
}

async function fetchPayloadFromAgent() {
  const text = document.getElementById(
    "naturalLanguageTextarea"
  ).value;

  const response = await fetch(
    "http://127.0.0.1:8000/parse",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        text
      })
    }
  );

  if (!response.ok) {
    throw new Error(
      "Failed to parse travel request"
    );
  }

  return await response.json();
}

document
  .getElementById("convertRequestButton")
  ?.addEventListener("click", async () => {
    try {
      const payload =
        await fetchPayloadFromAgent();

      document.getElementById(
        "payloadTextarea"
      ).value = JSON.stringify(
        payload,
        null,
        2
      );

      result.textContent = JSON.stringify(
        {
          ok: true,
          message:
            "Payload generated from FastAPI agent"
        },
        null,
        2
      );
    } catch (error) {
      result.textContent = JSON.stringify(
        {
          ok: false,
          error: error.message
        },
        null,
        2
      );
    }
  });

document
  .getElementById("openDashboardButton")
  ?.addEventListener("click", async () => {
    await chrome.tabs.create({
      url: "http://127.0.0.1:8000/"
    });
  });

document
  .getElementById("runFlowButton")
  ?.addEventListener("click", async () => {
    const request =
      getPayloadFromTextarea();

    if (!request) {
      return;
    }

    if (request.site !== "booking.com") {
      result.textContent = JSON.stringify(
        {
          ok: false,
          error: `Unsupported site: ${request.site}`
        },
        null,
        2
      );

      return;
    }

    await sendToContent({
      type: "RUN_BOOKING_FLOW",
      payload: request.payload
    });
  });

document
  .getElementById("recommendTopHotelsButton")
  ?.addEventListener("click", async () => {
    const request = getPayloadFromTextarea();

    if (!request) {
      return;
    }

    const response = await sendToContent({
      type: "GET_TOP_HOTEL_RECOMMENDATIONS",
      payload: {
        hotelPreference: request.payload.hotelPreference || [],
        limit: 3
      }
    });

    renderRecommendations(response?.recommendations || []);
  });

document
  .getElementById("clickBestMatchedHotelButton")
  ?.addEventListener("click", async () => {
    const request = getPayloadFromTextarea();

    if (!request) {
      return;
    }

    const response = await sendToContent({
      type: "CLICK_BEST_MATCHED_HOTEL",
      payload: {
        hotelPreference: request.payload.hotelPreference || []
      }
    });

    if (response?.hotelIndex !== undefined) {
      selectedRecommendationIndex = response.hotelIndex;
    }
  });

document
  .getElementById("confirmHotelSelectionButton")
  ?.addEventListener("click", async () => {
    if (selectedRecommendationIndex !== null) {
      await sendToContent({
        type: "CONFIRM_SPECIFIC_HOTEL_SELECTION",
        payload: {
          hotelIndex: selectedRecommendationIndex
        }
      });
      return;
    }

    await sendToContent({
      type: "CONFIRM_HOTEL_SELECTION"
    });
  });
