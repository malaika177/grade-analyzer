import re
import logging
import pdfplumber
from typing import Dict, List, Tuple, Optional


class GradeProcessor:
    """Process D2L grade PDFs to extract and calculate grades."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def process_pdf(self, filepath: str) -> Dict:
        """
        Process a D2L grade PDF and return calculated results.
        
        Args:
            filepath: Path to the PDF file
            
        Returns:
            Dictionary containing grade analysis results
        """
        try:
            # Extract text from PDF
            text = self._extract_pdf_text(filepath)

            # Parse grades and weights
            grade_items = self._parse_grades(text)

            if not grade_items:
                raise ValueError(
                    "No grades found in the PDF. Please ensure this is a valid D2L grades export."
                )

            # Calculate weighted average
            weighted_average = self._calculate_weighted_average(grade_items)

            # Convert to letter grade
            letter_grade = self._get_letter_grade(weighted_average)

            # Prepare results
            results = {
                'weighted_average':
                round(weighted_average, 2),
                'letter_grade':
                letter_grade,
                'grade_items':
                grade_items,
                'total_possible_points':
                self._calculate_total_possible_points(grade_items),
                'total_earned_points':
                self._calculate_total_earned_points(grade_items),
                'items_count':
                len(grade_items)
            }

            self.logger.info(
                f"Successfully processed PDF with {len(grade_items)} grade items"
            )
            return results

        except Exception as e:
            self.logger.error(f"Error processing PDF: {str(e)}")
            raise

    def _extract_pdf_text(self, filepath: str) -> str:
        """Extract text content from PDF file."""
        try:
            text = ""
            with pdfplumber.open(filepath) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"

            if not text.strip():
                raise ValueError(
                    "The PDF appears to be empty or contains no readable text."
                )

            return text

        except Exception as e:
            raise ValueError(f"Could not read PDF file: {str(e)}")

    def _parse_grades(self, text: str) -> List[Dict]:
        """
        Parse grades from D2L PDF text, including custom UDST format.
        """
        grade_items = []
        lines = text.split('\n')

        # Custom D2L format: "Quiz 2 8.24 / 10 2.75 / 3.33"
        d2l_pattern = r'(.+?)\s+(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)'

        # Additional fallback patterns (standard)
        fallback_patterns = [
            r'(.+?)\s+(\d+(?:\.\d+)?)/(\d+(?:\.\d+)?)\s+(?:Weight:|weight:)\s*(\d+(?:\.\d+)?)%',
            r'(.+?):\s*(\d+(?:\.\d+)?)\s+out\s+of\s+(\d+(?:\.\d+)?)\s*\((?:Weight:|weight:)\s*(\d+(?:\.\d+)?)%\)',
            r'(.+?)\s*\|\s*(\d+(?:\.\d+)?)\s*\|\s*(\d+(?:\.\d+)?)\s*\|\s*(\d+(?:\.\d+)?)%',
            r'(.+?)\s+(\d+(?:\.\d+)?)/(\d+(?:\.\d+)?)\s*\((\d+(?:\.\d+)?)%\)',
        ]

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # First try D2L format
            match = re.search(d2l_pattern, line)
            if match:
                name = match.group(1).strip()
                earned = float(match.group(4))  # weighted earned
                possible = float(match.group(5))  # weightedtotal
                if earned == 0.0:
                    continue
                percentage = round(
                    (earned / possible) * 100, 2) if possible > 0 else 0.0
                weight = possible

                grade_items.append({
                    'name': self._clean_assignment_name(name),
                    'earned': earned,
                    'possible': possible,
                    'weight': weight,
                    'percentage': percentage
                })
                self.logger.debug(
                    f"[D2L Format] Found grade item: {grade_items[-1]}")
                continue

            # Try fallback patterns
            for pattern in fallback_patterns:
                fallback_match = re.search(pattern, line, re.IGNORECASE)
                if fallback_match:
                    name = fallback_match.group(1).strip()
                    earned = float(fallback_match.group(2))
                    possible = float(fallback_match.group(3))
                    weight = float(fallback_match.group(4))

                    if possible <= 0 or weight <= 0:
                        continue

                    grade_items.append({
                        'name':
                        self._clean_assignment_name(name),
                        'earned':
                        earned,
                        'possible':
                        possible,
                        'weight':
                        weight,
                        'percentage':
                        round((earned / possible) * 100, 2)
                    })
                    self.logger.debug(
                        f"[Fallback] Found grade item: {grade_items[-1]}")
                    break

        return grade_items

    def _parse_alternative_format(self, text: str) -> List[Dict]:
        """Try alternative parsing methods for different D2L export formats."""
        grade_items = []

        # Look for percentage grades with weights
        lines = text.split('\n')

        # Pattern for lines like "Quiz 1: 85% (Weight: 15%)"
        percentage_pattern = r'(.+?):\s*(\d+(?:\.\d+)?)%\s*\((?:Weight:|weight:)\s*(\d+(?:\.\d+)?)%\)'

        for line in lines:
            line = line.strip()
            match = re.search(percentage_pattern, line, re.IGNORECASE)
            if match:
                name = match.group(1).strip()
                percentage = float(match.group(2))
                weight = float(match.group(3))

                if weight > 0:
                    grade_item = {
                        'name': self._clean_assignment_name(name),
                        'earned': percentage,
                        'possible': 100.0,
                        'weight': weight,
                        'percentage': percentage
                    }
                    grade_items.append(grade_item)

        return grade_items

    def _clean_assignment_name(self, name: str) -> str:
        """Clean up assignment names by removing common prefixes/suffixes."""
        # Remove common D2L prefixes
        prefixes_to_remove = [
            'Grade Item:', 'Item:', 'Assignment:', 'Quiz:', 'Test:', 'Exam:'
        ]

        for prefix in prefixes_to_remove:
            if name.startswith(prefix):
                name = name[len(prefix):].strip()

        # Remove trailing punctuation and whitespace
        name = name.rstrip(':|.-').strip()

        return name[:50]  # Limit length for display

    def _calculate_weighted_average(self, grade_items: List[Dict]) -> float:
        """Calculate weighted average from grade items."""
        if not grade_items:
            return 0.0

        total_weighted_points = 0.0
        total_weight = 0.0

        for item in grade_items:
            weight = item['weight'] / 100.0  # Convert percentage to decimal
            percentage = item['percentage']

            total_weighted_points += percentage * weight
            total_weight += weight

        # If weights don't add up to 100%, normalize them
        if total_weight > 0:
            if abs(total_weight - 1.0) > 0.01:  # If weights don't sum to 100%
                self.logger.warning(
                    f"Weights sum to {total_weight * 100:.1f}%, normalizing..."
                )
                return total_weighted_points / total_weight
            else:
                return total_weighted_points

        return 0.0

    def _calculate_total_possible_points(self,
                                         grade_items: List[Dict]) -> float:
        """Calculate total possible points considering weights."""
        return sum(item['possible'] * (item['weight'] / 100.0)
                   for item in grade_items)

    def _calculate_total_earned_points(self, grade_items: List[Dict]) -> float:
        """Calculate total earned points considering weights."""
        return sum(item['earned'] * (item['weight'] / 100.0)
                   for item in grade_items)

    def _get_letter_grade(self, percentage: float) -> str:

        if percentage >= 90:
            return 'A'
        elif percentage >= 85:
            return 'B+'
        elif percentage >= 80:
            return 'B'
        elif percentage >= 75:
            return 'C+'
        elif percentage >= 70:
            return 'C'
        elif percentage >= 65:
            return 'D+'
        elif percentage >= 60:
            return 'D'
        else:
            return 'F'
