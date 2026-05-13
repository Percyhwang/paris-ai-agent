let recommendedHotelIndex = null;
let recommendedHotels = [];
let automationSessionId = 0;
let automationLogs = [];

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function startAutomationSession(label) {
  automationSessionId += 1;
  automationLogs = [];
  logAutomation("session.start", { sessionId: automationSessionId, label });
}

function logAutomation(step, details = {}) {
  const entry = {
    sessionId: automationSessionId,
    timestamp: new Date().toISOString(),
    step,
    details
  };

  automationLogs.push(entry);
  console.log("[Travel Agent]", step, details);
  return entry;
}

function getAutomationLogs() {
  return automationLogs.slice(-200);
}

function buildErrorResult(error, details = {}) {
  logAutomation("step.error", { error, ...details });
  return {
    ok: false,
    error,
    logs: getAutomationLogs()
  };
}

function buildSuccessResult(data = {}) {
  return {
    ok: true,
    ...data,
    logs: getAutomationLogs()
  };
}

function isElementVisible(element) {
  if (!element) {
    return false;
  }

  const rect = element.getBoundingClientRect();
  const style = window.getComputedStyle(element);

  return (
    rect.width > 0 &&
    rect.height > 0 &&
    style.visibility !== "hidden" &&
    style.display !== "none"
  );
}

function describeElement(element) {
  if (!element) {
    return null;
  }

  return {
    tag: element.tagName,
    id: element.id || null,
    className: element.className || null,
    text: element.textContent?.trim()?.slice(0, 80) || null,
    ariaLabel: element.getAttribute("aria-label")
  };
}

function findFirstMatchingElement(selectors, options = {}) {
  const { root = document, visibleOnly = false } = options;

  for (const selector of selectors) {
    const element = root.querySelector(selector);

    if (!element) {
      continue;
    }

    if (visibleOnly && !isElementVisible(element)) {
      continue;
    }

    logAutomation("selector.match", {
      selector,
      element: describeElement(element)
    });

    return {
      element,
      selector
    };
  }

  logAutomation("selector.miss", { selectors });
  return null;
}

function findButtonLikeByText(textPatterns = [], options = {}) {
  const { root = document, visibleOnly = true } = options;
  const elements = Array.from(
    root.querySelectorAll("button, a, span, div")
  );

  for (const element of elements) {
    if (visibleOnly && !isElementVisible(element)) {
      continue;
    }

    const text = element.textContent?.trim();
    if (!text) {
      continue;
    }

    if (textPatterns.some((pattern) => text.includes(pattern))) {
      logAutomation("text.match", {
        patterns: textPatterns,
        element: describeElement(element)
      });
      return element;
    }
  }

  logAutomation("text.miss", { patterns: textPatterns });
  return null;
}

async function waitForCondition(check, options = {}) {
  const {
    timeoutMs = 5000,
    intervalMs = 250,
    label = "condition"
  } = options;
  const startedAt = Date.now();

  while (Date.now() - startedAt < timeoutMs) {
    const result = check();

    if (result) {
      logAutomation("wait.success", {
        label,
        elapsedMs: Date.now() - startedAt
      });
      return result;
    }

    await wait(intervalMs);
  }

  logAutomation("wait.timeout", { label, timeoutMs });
  return null;
}

async function safeClick(element, label) {
  if (!element) {
    return false;
  }

  element.scrollIntoView({
    behavior: "auto",
    block: "center",
    inline: "center"
  });

  await wait(100);

  try {
    element.click();
    logAutomation("click.native", {
      label,
      element: describeElement(element)
    });
    return true;
  } catch (error) {
    logAutomation("click.native_failed", {
      label,
      error: error.message
    });
  }

  try {
    simulateClick(element);
    logAutomation("click.simulated", {
      label,
      element: describeElement(element)
    });
    return true;
  } catch (error) {
    logAutomation("click.simulated_failed", {
      label,
      error: error.message
    });
    return false;
  }
}

function setNativeValue(element, value) {
  const valueSetter = Object.getOwnPropertyDescriptor(element, "value")?.set;
  const prototype = Object.getPrototypeOf(element);
  const prototypeValueSetter = Object.getOwnPropertyDescriptor(prototype, "value")?.set;

  if (prototypeValueSetter && valueSetter !== prototypeValueSetter) {
    prototypeValueSetter.call(element, value);
  } else if (valueSetter) {
    valueSetter.call(element, value);
  } else {
    element.value = value;
  }

  element.dispatchEvent(new Event("input", { bubbles: true }));
  element.dispatchEvent(new Event("change", { bubbles: true }));
}

function simulateClick(element) {
  const rect = element.getBoundingClientRect();
  const x = rect.left + rect.width / 2;
  const y = rect.top + rect.height / 2;
  const props = { bubbles: true, cancelable: true, view: window, clientX: x, clientY: y };

  element.dispatchEvent(new PointerEvent("pointerdown", props));
  element.dispatchEvent(new MouseEvent("mousedown", props));
  element.dispatchEvent(new PointerEvent("pointerup", props));
  element.dispatchEvent(new MouseEvent("mouseup", props));
  element.dispatchEvent(new MouseEvent("click", props));
}

async function fillDestination(destination) {
  logAutomation("destination.start", { destination });

  const inputMatch = findFirstMatchingElement(
    [
      'input[name="ss"]',
      '[data-testid="destination-container"] input',
      '[data-testid="destination-container"] input[type="search"]'
    ],
    { visibleOnly: true }
  );
  const input = inputMatch?.element;

  if (!input) {
    return buildErrorResult("Destination input not found");
  }

  input.focus();
  setNativeValue(input, destination);

  const firstSuggestion = await waitForCondition(
    () =>
      findFirstMatchingElement(
        [
          '[data-testid="autocomplete-result"]',
          '[data-testid="destination-container"] [role="option"]',
          'li[id^="autocomplete"] [role="option"]',
          '[data-testid="internal-input-container"] ~ ul li:first-child'
        ],
        { visibleOnly: true }
      )?.element,
    { timeoutMs: 2500, intervalMs: 200, label: "destination_suggestion" }
  );

  if (firstSuggestion) {
    await safeClick(firstSuggestion, "destination_suggestion");
    await wait(500);
  }

  return buildSuccessResult({
    field: "destination",
    value: destination
  });
}

async function openDatePicker() {
  logAutomation("dates.open.start");

  const dateButton = findFirstMatchingElement(
    [
      '[data-testid="searchbox-dates-container"]',
      '[data-testid="date-display-field-start"]',
      '[data-testid="date-display-field-end"]'
    ],
    { visibleOnly: true }
  )?.element;

  if (!dateButton) {
    return buildErrorResult("Date picker button not found");
  }

  await safeClick(dateButton, "date_picker_button");

  const dateGrid = await waitForCondition(
    () => getCalendarDateButtons().length > 0,
    { timeoutMs: 2500, intervalMs: 200, label: "calendar_open" }
  );

  if (!dateGrid) {
    return buildErrorResult("Calendar did not open");
  }

  return buildSuccessResult();
}

function getCalendarDateButtons() {
  return Array.from(document.querySelectorAll("[data-date]"));
}

function getVisibleDateRange() {
  const dates = getCalendarDateButtons()
    .map((button) => button.getAttribute("data-date"))
    .filter(Boolean)
    .sort();

  if (dates.length === 0) {
    return null;
  }

  return {
    first: dates[0],
    last: dates[dates.length - 1]
  };
}

function getNextMonthButton() {
  return (
    document.querySelector('[data-testid="calendar-arrow-right"]') ||
    document.querySelector('button[aria-label*="Next"]') ||
    document.querySelector('button[aria-label*="다음"]')
  );
}

function getPrevMonthButton() {
  return (
    document.querySelector('[data-testid="calendar-arrow-left"]') ||
    document.querySelector('button[aria-label*="Previous"]') ||
    document.querySelector('button[aria-label*="이전"]')
  );
}

function findDateButton(date) {
  return document.querySelector(`[data-date="${date}"]`);
}

function extractHotelCards() {
  const cards = Array.from(
    document.querySelectorAll('[data-testid="property-card"]')
  );

  const hotels = cards.map((card, index) => {
    const name = card
      .querySelector('[data-testid="title"]')
      ?.textContent?.trim();

    const price = card
      .querySelector('[data-testid="price-and-discounted-price"]')
      ?.textContent?.trim();

    const scoreText = card
      .querySelector('[data-testid="review-score"]')
      ?.textContent?.trim();

    const description = card.textContent.trim();

    return {
      index,
      name,
      price,
      scoreText,
      description
    };
  });

  logAutomation("hotels.extracted", {
    count: hotels.length
  });

  return hotels;
}

async function clickFirstHotelCard() {
  startAutomationSession("click_first_hotel");
  const firstCard = document.querySelector(
    '[data-testid="property-card"] a'
  );

  if (!firstCard) {
    return buildErrorResult("No hotel card found");
  }

  await safeClick(firstCard, "first_hotel_card");

  return buildSuccessResult();
}

function parseHotelScore(scoreText) {
  if (!scoreText) {
    return 0;
  }

  const match = scoreText.replace(",", ".").match(/\d+(\.\d+)?/);

  if (!match) {
    return 0;
  }

  return Number(match[0]);
}

function parsePriceValue(priceText) {
  if (!priceText) {
    return null;
  }

  const digits = priceText.replace(/[^\d]/g, "");

  if (!digits) {
    return null;
  }

  return Number(digits);
}

function extractCurrencyAmount(text = "") {
  const normalized = text.replace(/\s+/g, " ");
  const match = normalized.match(/[₩$€]\s?[\d,]+/);
  return match ? match[0].replace(/\s+/g, "") : null;
}

function cleanRoomName(text = "") {
  return text
    .replace(/\s+/g, " ")
    .replace(/남은 객실.*$/g, "")
    .replace(/선호 침대 선택.*$/g, "")
    .replace(/최대 투숙 인원.*$/g, "")
    .trim();
}

function buildRoomSummaryText(text = "") {
  return text
    .replace(/\s+/g, " ")
    .replace(/#policyModal_[^\s]+/g, "")
    .replace(/\{[^}]+\}/g, "")
    .replace(/opacity:\s*[\d.]+;?/g, "")
    .replace(/Booking\.com에서 부담.*?(?=총 요금|조식 포함|무료 취소|$)/g, "")
    .replace(/숙소 측에서 제공하는 할인.*?(?=총 요금|조식 포함|무료 취소|$)/g, "")
    .replace(/기존 요금 [₩$€\d, ]+/g, "")
    .replace(/현재 요금 [₩$€\d, ]+/g, "")
    .replace(/총 요금 [₩$€\d, +세금및기타요금()]+/g, "")
    .trim();
}

function extractRoomHighlights(normalizedText) {
  const highlights = [];

  if (includesAnyKeyword(normalizedText, ["더블침대"])) {
    highlights.push("더블침대");
  }
  if (includesAnyKeyword(normalizedText, ["싱글침대"])) {
    highlights.push("싱글침대");
  }
  if (includesAnyKeyword(normalizedText, ["도시 전망"])) {
    highlights.push("도시 전망");
  }
  if (includesAnyKeyword(normalizedText, ["무료 wifi", "무료 wi-fi"])) {
    highlights.push("무료 Wi-Fi");
  }
  if (includesAnyKeyword(normalizedText, ["전용 욕실"])) {
    highlights.push("전용 욕실");
  }

  return highlights;
}

function normalizeHotelText(text = "") {
  return text
    .toLowerCase()
    .replace(/\s+/g, " ")
    .trim();
}

function includesAnyKeyword(text, keywords = []) {
  return keywords.some((keyword) => text.includes(keyword));
}

function extractDistanceKm(text, keywords = []) {
  const lines = text.split(/\n|\./).map((line) => line.trim()).filter(Boolean);

  for (const line of lines) {
    const normalizedLine = normalizeHotelText(line);

    if (!includesAnyKeyword(normalizedLine, keywords)) {
      continue;
    }

    const kmMatch = normalizedLine.match(/(\d+(?:[.,]\d+)?)\s*km/);
    if (kmMatch) {
      return Number(kmMatch[1].replace(",", "."));
    }

    const meterMatch = normalizedLine.match(/(\d+)\s*m/);
    if (meterMatch) {
      return Number(meterMatch[1]) / 1000;
    }
  }

  return null;
}

function extractHotelSignals(hotel) {
  const description = hotel.description || "";
  const normalizedDescription = normalizeHotelText(description);
  const priceValue = parsePriceValue(hotel.price);
  const reviewScore = parseHotelScore(hotel.scoreText);
  let valueBucket = null;
  let reviewTier = null;
  let luxuryTier = null;

  if (priceValue !== null && reviewScore > 0) {
    if (priceValue <= 200000 && reviewScore >= 8.5) {
      valueBucket = "strong";
    } else if (priceValue <= 350000 && reviewScore >= 8) {
      valueBucket = "good";
    } else if (priceValue <= 500000 && reviewScore >= 7.5) {
      valueBucket = "moderate";
    }
  }

  if (reviewScore >= 9) {
    reviewTier = "excellent";
  } else if (reviewScore >= 8.5) {
    reviewTier = "strong";
  } else if (reviewScore >= 8) {
    reviewTier = "good";
  }

  const mentionsLuxury = includesAnyKeyword(normalizedDescription, [
    "럭셔리",
    "고급",
    "프리미엄",
    "5성급",
    "luxury",
    "premium",
    "upscale"
  ]);

  if (mentionsLuxury || priceValue !== null) {
    if (
      mentionsLuxury &&
      priceValue !== null &&
      priceValue >= 450000 &&
      reviewScore >= 8.5
    ) {
      luxuryTier = "strong";
    } else if (
      mentionsLuxury ||
      (priceValue !== null && priceValue >= 350000 && reviewScore >= 8)
    ) {
      luxuryTier = "good";
    }
  }

  const signals = {
    priceValue,
    reviewScore,
    reviewTier,
    hasBreakfast: includesAnyKeyword(normalizedDescription, [
      "조식 포함",
      "조식 제공",
      "무료 조식",
      "breakfast included",
      "breakfast",
      "free breakfast"
    ]),
    hasMetroAccess: includesAnyKeyword(normalizedDescription, [
      "지하철",
      "지하철 연결",
      "역",
      "역세권",
      "metro",
      "subway"
    ]),
    mentionsEiffel: includesAnyKeyword(normalizedDescription, [
      "에펠",
      "에펠탑",
      "eiffel"
    ]),
    eiffelDistanceKm: extractDistanceKm(normalizedDescription, [
      "에펠",
      "에펠탑",
      "eiffel"
    ]),
    valueBucket,
    mentionsLuxury,
    luxuryTier
  };

  return signals;
}

function calculateHotelRankingScore(hotel, preferences = []) {
  let score = parseHotelScore(hotel.scoreText);
  const reasons = [];

  if (score > 0) {
    reasons.push(`리뷰 점수: ${score}`);
  }

  const signals = extractHotelSignals(hotel);

  if (
    preferences.includes("breakfast_included") &&
    signals.hasBreakfast
  ) {
    score += 1.5;
    reasons.push("조식 포함 정보가 표시됨");
  }

  if (
    preferences.includes("near_eiffel_tower") &&
    signals.mentionsEiffel
  ) {
    score += 2;
    reasons.push("에펠탑 관련 위치 정보가 표시됨");
  }

  if (
    preferences.includes("near_eiffel_tower") &&
    signals.eiffelDistanceKm !== null
  ) {
    if (signals.eiffelDistanceKm <= 1) {
      score += 2;
      reasons.push(`에펠탑까지 약 ${signals.eiffelDistanceKm}km`);
    } else if (signals.eiffelDistanceKm <= 2.5) {
      score += 1;
      reasons.push(`에펠탑과 비교적 가까움: 약 ${signals.eiffelDistanceKm}km`);
    }
  }

  if (
    preferences.includes("near_metro") &&
    signals.hasMetroAccess
  ) {
    score += 1.5;
    reasons.push("지하철 접근성 정보가 표시됨");
  }

  if (
    preferences.includes("value_for_money") &&
    signals.valueBucket
  ) {
    if (signals.valueBucket === "strong") {
      score += 2;
      reasons.push("가격 대비 평점이 매우 좋은 편");
    } else if (signals.valueBucket === "good") {
      score += 1.5;
      reasons.push("가격 대비 평점이 좋은 편");
    } else if (signals.valueBucket === "moderate") {
      score += 1;
      reasons.push("가격 대비 무난한 조건으로 보임");
    }
  }

  if (
    preferences.includes("high_review_score") &&
    signals.reviewTier
  ) {
    if (signals.reviewTier === "excellent") {
      score += 2;
      reasons.push("리뷰 평점이 매우 높음");
    } else if (signals.reviewTier === "strong") {
      score += 1.5;
      reasons.push("리뷰 평점이 높은 편");
    } else if (signals.reviewTier === "good") {
      score += 1;
      reasons.push("리뷰 평점이 안정적인 편");
    }
  }

  if (
    preferences.includes("luxury_stay") &&
    signals.luxuryTier
  ) {
    if (signals.luxuryTier === "strong") {
      score += 2;
      reasons.push("럭셔리 숙소로 보이는 신호가 강함");
    } else if (signals.luxuryTier === "good") {
      score += 1.5;
      reasons.push("고급 숙소로 보이는 정보가 있음");
    }
  }

  return {
    score,
    reasons,
    signals
  };
}

function rankHotels(preferences = [], limit = 3) {
  const cards = Array.from(
    document.querySelectorAll('[data-testid="property-card"]')
  );

  if (!cards.length) {
    return [];
  }

  const rankedHotels = cards
    .map((card, index) => {
      const hotel = {
        index,
        name: card.querySelector('[data-testid="title"]')?.textContent?.trim(),
        price: card
          .querySelector('[data-testid="price-and-discounted-price"]')
          ?.textContent?.trim(),
        scoreText: card
          .querySelector('[data-testid="review-score"]')
          ?.textContent?.trim(),
        description: card.textContent.trim()
      };

      const rankingResult = calculateHotelRankingScore(
        hotel,
        preferences
      );

      return {
        ...hotel,
        rankingScore: rankingResult.score,
        reasons: rankingResult.reasons,
        signals: rankingResult.signals
      };
    })
    .sort((a, b) => b.rankingScore - a.rankingScore)
    .slice(0, limit);

  recommendedHotels = rankedHotels;

  if (rankedHotels[0]) {
    recommendedHotelIndex = rankedHotels[0].index;
  }

  logAutomation("recommendation.ranked", {
    limit,
    count: rankedHotels.length,
    hotels: rankedHotels.map((hotel) => ({
      index: hotel.index,
      name: hotel.name,
      rankingScore: hotel.rankingScore,
      reasons: hotel.reasons
    }))
  });

  return rankedHotels;
}

async function confirmRecommendedHotelSelection() {
  startAutomationSession("confirm_recommended_hotel");
  logAutomation("recommendation.confirm.start", {
    recommendedHotelIndex
  });

  if (recommendedHotelIndex === null) {
    return buildErrorResult("No recommended hotel index stored");
  }

  const cards = Array.from(
    document.querySelectorAll('[data-testid="property-card"]')
  );

  const card = cards[recommendedHotelIndex];

  if (!card) {
    return buildErrorResult("Recommended hotel card not found", {
      recommendedHotelIndex,
      availableCards: cards.length
    });
  }

  const hotelLink = card.querySelector("a");

  if (!hotelLink) {
    return buildErrorResult("No hotel link found");
  }

  await safeClick(hotelLink, "recommended_hotel_link");

  return buildSuccessResult({
    message: "Hotel selection triggered"
  });
}

async function confirmSpecificHotelSelection(hotelIndex) {
  startAutomationSession("confirm_specific_hotel");
  logAutomation("recommendation.confirm_specific.start", {
    hotelIndex
  });

  const cards = Array.from(
    document.querySelectorAll('[data-testid="property-card"]')
  );

  const card = cards[hotelIndex];

  if (!card) {
    return buildErrorResult("Selected hotel card not found", {
      hotelIndex,
      availableCards: cards.length
    });
  }

  const hotelLink = card.querySelector("a");

  if (!hotelLink) {
    return buildErrorResult("No hotel link found");
  }

  recommendedHotelIndex = hotelIndex;
  await safeClick(hotelLink, "selected_hotel_link");

  return buildSuccessResult({
    hotelIndex,
    message: "Selected hotel navigation triggered"
  });
}

function getTopHotelRecommendations(preferences = [], limit = 3) {
  startAutomationSession("recommend_top_hotels");
  logAutomation("recommendation.top.start", {
    preferences,
    limit
  });

  const recommendations = rankHotels(preferences, limit);

  if (!recommendations.length) {
    return buildErrorResult("No hotel cards found");
  }

  return buildSuccessResult({
    recommendations,
    recommendedHotelIndex
  });
}

function clickBestMatchedHotel(preferences = []) {
  startAutomationSession("recommend_best_hotel");
  logAutomation("recommendation.start", { preferences });
  const rankedHotels = rankHotels(preferences, 1);

  if (!rankedHotels.length) {
    return buildErrorResult("No hotel cards found");
  }
  const bestHotel = rankedHotels[0];

  logAutomation("recommendation.selected", {
    recommendedHotelIndex,
    selectedHotel: bestHotel.name,
    rankingScore: bestHotel.rankingScore,
    reasons: bestHotel.reasons
  });

  return buildSuccessResult({
    selectedHotel: bestHotel.name,
    rankingScore: bestHotel.rankingScore,
    preferences,
    reasons: bestHotel.reasons,
    hotelIndex: bestHotel.index
  });
}

function extractRoomOptions() {
  startAutomationSession("extract_room_options");

  const availabilityTables = [
    ...Array.from(document.querySelectorAll('[data-testid="availability-table"]')),
    ...Array.from(document.querySelectorAll("table")).filter((table) =>
      table.textContent?.includes("객실 유형") ||
      table.textContent?.includes("선택사항") ||
      table.textContent?.includes("객실 선택")
    )
  ];

  logAutomation("rooms.table_candidates", {
    count: availabilityTables.length,
    candidates: availabilityTables.slice(0, 5).map((table, index) => ({
      index,
      textPreview: table.textContent?.trim().replace(/\s+/g, " ").slice(0, 220) || "",
      rowCount: table.querySelectorAll("tr").length
    }))
  });

  const availabilityTable = availabilityTables[0];

  if (!availabilityTable) {
    return buildErrorResult("Room options not found on current page", {
      url: window.location.href
    });
  }

  const rows = Array.from(availabilityTable.querySelectorAll("tbody tr"));

  logAutomation("rooms.table_rows", {
    rowCount: rows.length,
    rows: rows.slice(0, 8).map((row, index) => {
      const cells = Array.from(row.querySelectorAll("td"));
      return {
        index,
        cellCount: cells.length,
        hasSelect: !!row.querySelector("select"),
        hasPriceLikeText: /₩|\$|€|krw|usd|eur/i.test(row.textContent || ""),
        textPreview: row.textContent?.trim().replace(/\s+/g, " ").slice(0, 180) || ""
      };
    })
  });

  const roomOptions = [];
  let currentRoomName = null;

  rows.forEach((row) => {
    const cells = Array.from(row.querySelectorAll("td"));

    if (!cells.length) {
      return;
    }

    const cellTexts = cells.map((cell) =>
      cell.textContent?.trim().replace(/\s+/g, " ") || ""
    );
    const rowText = row.textContent?.trim().replace(/\s+/g, " ") || "";
    const normalizedRowText = normalizeHotelText(rowText);

    const roomNameCandidate =
      cells[0]?.querySelector("a, span, div, h3, h4")?.textContent?.trim() ||
      cellTexts[0];

    if (
      roomNameCandidate &&
      roomNameCandidate.length > 3 &&
      !/객실 유형|선택사항|객실 선택|최대 투숙 인원|총 요금/.test(roomNameCandidate) &&
      !/₩|\$|€|krw|usd|eur/i.test(roomNameCandidate)
    ) {
      currentRoomName = roomNameCandidate;
    }

    const priceCell = cells.find((cell) =>
      /₩|\$|€|krw|usd|eur/i.test(cell.textContent || "")
    ) || null;
    const optionCell = cells.find((cell) =>
      includesAnyKeyword(normalizeHotelText(cell.textContent || ""), [
        "조식",
        "무료 취소",
        "환불 불가",
        "현장 결제",
        "숙소에서 결제",
        "선결제 필요 없음",
        "포함사항"
      ])
    ) || null;
    const selectCell = cells.find((cell) => cell.querySelector("select")) || null;

    const looksLikeOptionRow =
      !!priceCell &&
      !!selectCell;

    if (!looksLikeOptionRow) {
      return;
    }

    const combinedText = rowText;

    roomOptions.push({
      index: roomOptions.length,
      roomName: cleanRoomName(currentRoomName || `객실 옵션 ${roomOptions.length + 1}`),
      price:
        Array.from((priceCell || row).querySelectorAll("span, div")).find((el) =>
          /₩|\$|€|krw|usd|eur/i.test(el.textContent || "")
        )?.textContent?.trim() ||
        priceCell?.textContent?.trim().replace(/\s+/g, " ") ||
        "가격 정보 없음",
      displayPrice:
        extractCurrencyAmount(
          Array.from((priceCell || row).querySelectorAll("span, div"))
            .map((el) => el.textContent?.trim() || "")
            .join(" ")
        ) ||
        extractCurrencyAmount(priceCell?.textContent || "") ||
        "가격 정보 없음",
      text: buildRoomSummaryText(combinedText),
      breakfastIncluded: includesAnyKeyword(normalizedRowText, [
        "조식 포함",
        "조식 제공",
        "breakfast included",
        "breakfast"
      ]),
      freeCancellation: includesAnyKeyword(normalizedRowText, [
        "무료 취소",
        "free cancellation",
        "취소 가능"
      ]),
      payLater: includesAnyKeyword(normalizedRowText, [
        "현장 결제",
        "pay later",
        "no prepayment",
        "선결제 필요 없음",
        "숙소에서 결제"
      ]),
      hasSelector: !!selectCell,
      optionSummary:
        buildRoomSummaryText(optionCell?.textContent?.trim().replace(/\s+/g, " ") || ""),
      highlights: extractRoomHighlights(normalizedRowText)
    });
  });

  if (!roomOptions.length) {
    return buildErrorResult("Room option rows were not detected", {
      url: window.location.href
    });
  }

  logAutomation("rooms.extracted", {
    count: roomOptions.length,
    roomNames: roomOptions.map((option) => option.roomName)
  });

  return buildSuccessResult({
    roomOptions
  });
}

async function findDateButtonWithNavigation(date, maxClicks = 12) {
  for (let i = 0; i <= maxClicks; i++) {
    const dateButton = findDateButton(date);

    if (dateButton) {
      logAutomation("dates.found", { date, navigationClicks: i });
      return dateButton;
    }

    const range = getVisibleDateRange();

    if (!range) {
      return null;
    }

    if (date < range.first) {
      const prevButton = getPrevMonthButton();
      if (!prevButton) return null;
      await safeClick(prevButton, "calendar_previous_month");
      await wait(500);
      continue;
    }

    if (date > range.last) {
      const nextButton = getNextMonthButton();
      if (!nextButton) return null;
      await safeClick(nextButton, "calendar_next_month");
      await wait(500);
      continue;
    }

    return null;
  }

  return null;
}

async function selectBookingDates(checkIn, checkOut) {
  logAutomation("dates.start", { checkIn, checkOut });
  const opened = await openDatePicker();

  if (!opened.ok) {
    return opened;
  }

  const checkInButton = await findDateButtonWithNavigation(checkIn);

  if (!checkInButton) {
    return buildErrorResult(`Check-in date not found after navigation: ${checkIn}`);
  }

  await safeClick(checkInButton, "checkin_date");
  await wait(500);

  const checkOutButton = await findDateButtonWithNavigation(checkOut);

  if (!checkOutButton) {
    return buildErrorResult(`Check-out date not found after navigation: ${checkOut}`);
  }

  await safeClick(checkOutButton, "checkout_date");
  await wait(500);

  return buildSuccessResult({
    field: "dates",
    checkIn,
    checkOut
  });
}

async function openGuestSelector() {
  logAutomation("guests.open.start");

  const guestButton = findFirstMatchingElement(
    [
      '[data-testid="occupancy-config"]',
      '[data-testid="searchbox-occupancy"]'
    ],
    { visibleOnly: true }
  )?.element;

  if (!guestButton) {
    return buildErrorResult("Guest selector button not found");
  }

  await safeClick(guestButton, "guest_selector_button");

  const popupOpened = await waitForCondition(
    () => document.querySelector('[data-testid="occupancy-popup"]'),
    { timeoutMs: 2500, intervalMs: 200, label: "occupancy_popup_open" }
  );

  if (!popupOpened) {
    return buildErrorResult("Occupancy popup did not open");
  }

  return buildSuccessResult();
}

function getOccupancyPopup() {
  return document.querySelector('[data-testid="occupancy-popup"]');
}

function getOccupancyIconButtons() {
  const popup = getOccupancyPopup();

  if (!popup) return null;

  // 순서: 성인-, 성인+, 어린이-, 어린이+, 객실-, 객실+
  return Array.from(popup.querySelectorAll("button")).filter(
    (b) => !b.textContent.trim()
  );
}

function findOccupancyRow(keywords = []) {
  const popup = getOccupancyPopup();

  if (!popup) return null;

  const candidates = Array.from(popup.querySelectorAll("div, li")).filter((el) => {
    if (!isElementVisible(el)) {
      return false;
    }

    const text = el.textContent?.trim();
    if (!text) {
      return false;
    }

    const buttonCount = el.querySelectorAll("button").length;
    const numericCount = Array.from(el.querySelectorAll("span, div")).filter((child) =>
      /^\d+$/.test(child.textContent.trim())
    ).length;

    return (
      keywords.some((keyword) => text.includes(keyword)) &&
      buttonCount >= 2 &&
      numericCount >= 1 &&
      text.length < 80
    );
  });

  const row =
    candidates
      .sort((a, b) => a.textContent.trim().length - b.textContent.trim().length)[0] ||
    null;

  logAutomation("occupancy.row_lookup", {
    keywords,
    matched: !!row,
    text: row?.textContent?.trim()?.slice(0, 120) || null
  });

  return row;
}

function getAdultRow() {
  return findOccupancyRow(["성인", "Adults", "Adult"]);
}

function getAdultCountElement() {
  const adultRow = getAdultRow();

  if (adultRow) {
    const countElement = Array.from(adultRow.querySelectorAll("span, div")).find((el) =>
      /^\d+$/.test(el.textContent.trim())
    );

    if (countElement) {
      return countElement;
    }
  }

  const popup = getOccupancyPopup();
  if (!popup) return null;

  return Array.from(popup.querySelectorAll("span, div")).find((el) =>
    /^\d+$/.test(el.textContent.trim())
  );
}

function getButtonsFromRow(row) {
  if (!row) {
    return [];
  }

  return Array.from(row.querySelectorAll("button")).filter(isElementVisible);
}

function getAdultButtonCandidates(direction) {
  const adultRow = getAdultRow();
  const rowButtons = getButtonsFromRow(adultRow);
  const countElement = getAdultCountElement();

  const labelledButton = pickButtonByAria(
    rowButtons,
    direction === "up"
      ? ["성인 수 늘리기", "Increase number of Adults", "Increase number of Adult", "성인 증가"]
      : ["성인 수 줄이기", "Decrease number of Adults", "Decrease number of Adult", "성인 감소"]
  );

  if (labelledButton) {
    return [labelledButton];
  }

  if (countElement) {
    const orderedButtons = rowButtons
      .map((button) => ({
        button,
        deltaX:
          button.getBoundingClientRect().left -
          countElement.getBoundingClientRect().left
      }))
      .sort((a, b) => a.deltaX - b.deltaX)
      .map((item) => item.button);

    const directionalButtons =
      direction === "up"
        ? orderedButtons.filter(
            (button) =>
              button.getBoundingClientRect().left >
              countElement.getBoundingClientRect().left
          )
        : orderedButtons.filter(
            (button) =>
              button.getBoundingClientRect().left <
              countElement.getBoundingClientRect().left
          );

    if (directionalButtons.length) {
      return directionalButtons;
    }
  }

  return direction === "up" ? rowButtons.slice().reverse() : rowButtons;
}

function getRightmostButton(row) {
  const buttons = getButtonsFromRow(row);

  return (
    buttons
      .slice()
      .sort(
        (a, b) =>
          b.getBoundingClientRect().left - a.getBoundingClientRect().left
      )[0] || null
  );
}

function getLeftmostButton(row) {
  const buttons = getButtonsFromRow(row);

  return (
    buttons
      .slice()
      .sort(
        (a, b) =>
          a.getBoundingClientRect().left - b.getBoundingClientRect().left
      )[0] || null
  );
}

function pickButtonByAria(buttons, keywords) {
  return buttons.find((button) => {
    const ariaLabel = button.getAttribute("aria-label") || "";
    return keywords.some((keyword) => ariaLabel.includes(keyword));
  }) || null;
}

function getAdultMinusButton() {
  const adultRow = getAdultRow();
  return getLeftmostButton(adultRow) || getAdultButtonCandidates("down")[0] || null;
}

function getAdultPlusButton() {
  const adultRow = getAdultRow();
  return getRightmostButton(adultRow) || getAdultButtonCandidates("up")[0] || null;
}

async function adjustAdultCountOnce(direction, current) {
  const primaryButton =
    direction === "up" ? getAdultPlusButton() : getAdultMinusButton();
  const fallbackCandidates = getAdultButtonCandidates(direction);
  const buttonCandidates = [
    ...(primaryButton ? [primaryButton] : []),
    ...fallbackCandidates.filter((button) => button !== primaryButton)
  ];

  logAutomation("guests.button_candidates", {
    direction,
    count: buttonCandidates.length,
    candidates: buttonCandidates.map(describeElement)
  });

  for (const [index, button] of buttonCandidates.entries()) {
    await safeClick(button, direction === "up" ? "adult_plus" : "adult_minus");
    await wait(250);

    let nextElement = getAdultCountElement();
    let next = parseInt(nextElement?.textContent.trim(), 10);

    if (next === current) {
      simulateClick(button);
      logAutomation("click.simulated_forced", {
        direction,
        candidateIndex: index,
        button: describeElement(button)
      });
      await wait(300);
      nextElement = getAdultCountElement();
      next = parseInt(nextElement?.textContent.trim(), 10);
    }

    if (next === current) {
      const rect = button.getBoundingClientRect();
      const targetX =
        direction === "up" ? rect.right - rect.width / 3 : rect.left + rect.width / 3;
      const targetY = rect.top + rect.height / 2;
      const coordinateProps = {
        bubbles: true,
        cancelable: true,
        view: window,
        clientX: targetX,
        clientY: targetY
      };

      button.dispatchEvent(new PointerEvent("pointerdown", coordinateProps));
      button.dispatchEvent(new MouseEvent("mousedown", coordinateProps));
      button.dispatchEvent(new PointerEvent("pointerup", coordinateProps));
      button.dispatchEvent(new MouseEvent("mouseup", coordinateProps));
      button.dispatchEvent(new MouseEvent("click", coordinateProps));

      logAutomation("click.coordinate_forced", {
        direction,
        candidateIndex: index,
        button: describeElement(button),
        x: targetX,
        y: targetY
      });

      await wait(300);
      nextElement = getAdultCountElement();
      next = parseInt(nextElement?.textContent.trim(), 10);
    }

    logAutomation(
      direction === "up" ? "guests.count_after_plus" : "guests.count_after_minus",
      {
        current,
        next,
        candidateIndex: index,
        countElement: describeElement(nextElement),
        button: describeElement(button)
      }
    );

    if (!isNaN(next) && next !== current) {
      return next;
    }
  }

  return current;
}

async function setAdultCount(targetAdults) {
  logAutomation("guests.set_adults.start", { targetAdults });
  const opened = await openGuestSelector();

  if (!opened.ok) return opened;

  await wait(500);

  const countElement = getAdultCountElement();

  if (!countElement) {
    return buildErrorResult("Adult count element not found");
  }

  let current = parseInt(countElement.textContent.trim(), 10);

  logAutomation("guests.current_count", {
    current,
    countElement: describeElement(countElement)
  });

  if (isNaN(current)) {
    return buildErrorResult("Failed to read adult count");
  }

  const MAX_CLICKS = 10;

  for (let i = 0; current < targetAdults && i < MAX_CLICKS; i++) {
    if (!getAdultPlusButton()) {
      return buildErrorResult("Plus button not found");
    }

    const next = await adjustAdultCountOnce("up", current);

    if (isNaN(next) || next === current) {
      return buildErrorResult(`Adult count stuck at ${current}`, {
        targetAdults,
        direction: "up"
      });
    }

    current = next;
  }

  for (let i = 0; current > targetAdults && i < MAX_CLICKS; i++) {
    if (!getAdultMinusButton()) {
      return buildErrorResult("Minus button not found");
    }

    const next = await adjustAdultCountOnce("down", current);

    if (isNaN(next) || next === current) {
      return buildErrorResult(`Adult count stuck at ${current}`, {
        targetAdults,
        direction: "down"
      });
    }

    current = next;
  }

  return buildSuccessResult({
    field: "adults",
    value: targetAdults
  });
}

async function clickGuestDoneButton() {
  logAutomation("guests.done.start");
  const popup = document.querySelector('[data-testid="occupancy-popup"]');

  if (!popup) {
    return buildErrorResult("Occupancy popup not found");
  }

  const doneButton =
    popup.querySelector('[data-testid="occupancy-popup-continue-button"]') ||
    Array.from(popup.querySelectorAll("button")).find((btn) => {
      const text = btn.textContent.trim();
      return text === "완료" || text === "Done" || text === "확인";
    });

  if (!doneButton) {
    return buildErrorResult("Guest done button not found");
  }

  await safeClick(doneButton, "guest_done_button");

  const popupClosed = await waitForCondition(
    () => !document.querySelector('[data-testid="occupancy-popup"]'),
    { timeoutMs: 2500, intervalMs: 200, label: "occupancy_popup_closed" }
  );

  if (!popupClosed) {
    return buildErrorResult("Occupancy popup did not close after Done");
  }

  return buildSuccessResult();
}

async function clickSearchButton() {
  logAutomation("search.start");

  const searchButton = findFirstMatchingElement(
    [
      '[data-testid="search-button"]',
      'button[type="submit"]'
    ],
    { visibleOnly: true }
  )?.element;

  if (!searchButton) {
    return buildErrorResult("Search button not found");
  }

  await safeClick(searchButton, "search_button");

  const navigationDetected = await waitForCondition(
    () =>
      window.location.href.includes("/searchresults") ||
      document.querySelector('[data-testid="property-card"]') ||
      document.querySelector('[data-testid="property-card-container"]'),
    { timeoutMs: 10000, intervalMs: 400, label: "search_results_navigation" }
  );

  if (!navigationDetected) {
    return buildErrorResult("Search results page did not load");
  }

  return buildSuccessResult({
    navigated: true,
    url: window.location.href
  });
}

async function runBookingFlow(data) {
  try {
    startAutomationSession("run_booking_flow");
    logAutomation("flow.start", { payload: data });

    const destinationResult = await fillDestination(data.destination);
    if (!destinationResult.ok) return destinationResult;

    await wait(800);

    const datesResult = await selectBookingDates(data.checkIn, data.checkOut);
    if (!datesResult.ok) return datesResult;

    await wait(800);

    const adultsResult = await setAdultCount(data.adults);
    if (!adultsResult.ok) return adultsResult;

    await wait(800);

    const doneResult = await clickGuestDoneButton();
    if (!doneResult.ok) return doneResult;

    await wait(500);

    const searchResult = await clickSearchButton();
    if (!searchResult.ok) {
      return searchResult;
    }

    logAutomation("flow.success", { finalUrl: window.location.href });
    return buildSuccessResult({
      message: "Booking flow completed",
      finalUrl: window.location.href
    });

  } catch (error) {
    console.error("[Travel Agent] Flow failed:", error);
    return buildErrorResult(error.message);
  }
}
