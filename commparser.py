#!/usr/bin/env python3
"""
Module for parsing draft-ietf-grow-yang-bgp-communities style BGP community definitions
Based on code written by Martin Pels
"""

import re
import json
import requests


class BGPCommunityParser:
    """
    An object to keep track of one or more draft-ietf-grow-yang-bgp-communities style BGP community definitions
    and do lookups on them.
    """
    def __init__(self, sources=None):
        self.comm_regular = []
        self.comm_large = []
        self.comm_extended = []
        self.sources = []

        if not sources:
            return

        if not isinstance(sources, list):
            sources = [sources]

        for source in sources:
            self.load_source(source)

    def load_source(self, source: str):
        """
        Load a draft-yang-bgp-communities style BGP community definition from
        an URL or file.
        """
        jdata = None
        if source.startswith("http://") or source.startswith("https://"):
            jdata = requests.get(source, timeout=5).json()
        else:
            jdata = json.load(source)

        self.comm_regular += jdata["draft-ietf-grow-yang-bgp-communities:bgp-communities"]["regular"]
        self.comm_large += jdata["draft-ietf-grow-yang-bgp-communities:bgp-communities"]["large"]
        self.comm_extended += jdata["draft-ietf-grow-yang-bgp-communities:bgp-communities"]["extended"]
        self.sources.append(source)

    def __str__(self):
        """
        Simple string representation of the object.
        """
        return f"BGPCommunityParser object with {len(self.sources)} sources, " \
            f"{len(self.comm_regular)} regular, " \
            f"{len(self.comm_large)} large and {len(self.comm_extended)} communities"

    def parse_community(self, community: str) -> str:
        """
        Lookup a community string in the loaded community definitions.
        """
        if re.match(r"^\d+:\d+$", community):
            return self.parse_regular_community(community)
        if re.match(r"^\d+:\d+:\d+$", community):
            return self.parse_large_community(community)
        if re.match(r"^0x\d\d:0x\d\d:\d+:\d+$", community):
            return self.parse_extended_community(community)
        return None

    def parse_regular_community(self, community: str) -> str:
        """
        Process RFC1997 community
        """
        asn, content = community.split(":", 1)

        found = self._try_candidates_regular(asn, content, self.comm_regular)
        if found:
            fieldvals = self._candidate2fields(content, found["localadmin"])
            return self._print_match(community, found, fieldvals)

        return None

    def parse_large_community(self, community: str) -> str:
        """
        Process RFC8092 community
        """
        asn, content1, content2 = community.split(":", 2)

        found = self._try_candidates_large(asn, content1, content2, self.comm_large)
        if found:
            fieldvals = self._candidate2fields_large(
                content1, content2, found["localdatapart1"], found["localdatapart2"]
            )
            return self._print_match(community, found, fieldvals)

        return None

    def parse_extended_community(self, community: str) -> str:
        """
        Process RFC4360 community
        """
        extype, exsubtype, asn, content = community.split(":", 3)

        found = self._try_candidates_extended(
            extype, exsubtype, asn, content, self.comm_extended
        )
        if found:
            fieldvals = self._candidate2fields(content, found["localadmin"])
            return self._print_match(community, found, fieldvals)

        return None

    def _try_candidates_regular(self, asn: str, content: str, candidates: list):
        """
        Try to find a matching Regular Community amongst candidate JSON definitions
        """
        for candidate in candidates:
            if asn != str(candidate["globaladmin"]):
                continue
            if "format" in candidate["localadmin"]:
                if candidate["localadmin"]["format"] == "binary":
                    content = self._decimal2bits(content, 16)
            if self._try_candidate_fields(content, candidate["localadmin"]["fields"]):
                return candidate
        return False

    def _try_candidates_large(self, asn, content1, content2, candidates):
        """
        Try to find a matching Large Community amongst candidate JSON definitions
        """
        for candidate in candidates:
            if asn != str(candidate["globaladmin"]):
                continue
            if "format" in candidate["localdatapart1"]:
                if candidate["localdatapart1"]["format"] == "binary":
                    content1 = self._decimal2bits(content1, 32)
            if "format" in candidate["localdatapart2"]:
                if candidate["localdatapart2"]["format"] == "binary":
                    content2 = self._decimal2bits(content2, 32)
            if self._try_candidate_fields(
                content1, candidate["localdatapart1"]["fields"]
            ) and self._try_candidate_fields(
                content2, candidate["localdatapart2"]["fields"]
            ):
                return candidate
        return False

    def _try_candidates_extended(self, extype, exsubtype, asn, content, candidates):
        """
        Try to find a matching Extended Community amongst candidate JSON definitions
        """
        for candidate in candidates:
            contentstring = content
            if int(extype, 16) != candidate["type"]:
                continue
            if int(exsubtype, 16) != candidate["subtype"]:
                continue
            if "asn" in candidate:
                if asn != str(candidate["asn"]):
                    continue
            elif "asn4" in candidate:
                if asn != str(candidate["asn4"]):
                    continue
            else:
                continue
            if "format" in candidate["localadmin"]:
                if candidate["localadmin"]["format"] == "binary":
                    if "asn4" in candidate:
                        contentstring = self._decimal2bits(content, 16)
                    else:
                        contentstring = self._decimal2bits(content, 32)
            if self._try_candidate_fields(
                contentstring, candidate["localadmin"]["fields"]
            ):
                return candidate
        return False

    def _try_candidate_fields(self, content, cfields):
        """
        Try to match fields from a single candidate JSON definition
        """
        pos = 0
        for cfield in cfields:
            if "length" in cfield:
                value = content[pos: pos + cfield["length"]]
            else:
                value = content

            pattern = cfield["pattern"]
            if pattern.startswith("^"):
                pattern = pattern[1:]
            if pattern.endswith("$"):
                pattern = pattern[:-1]
            if not re.match("^{}$".format(pattern), value):
                # print('{} != {}'.format(pattern,value))
                return False

            if "length" in cfield:
                pos = pos + cfield["length"]
        return True

    def _candidate2fields(self, contentbits, clocaladmin):
        """
        Link values from tested community to field names in matched candidate
        """
        fields = {}
        pos = 0
        if "format" in clocaladmin:
            if clocaladmin["format"] == "binary":
                contentbits = self._decimal2bits(contentbits, 16)
        for fid, field in enumerate(clocaladmin["fields"]):
            if "length" in field:
                length = field["length"]
            else:
                length = len(contentbits)
            fields[fid] = contentbits[pos: pos + length]
            pos = pos + length
        return fields

    def _candidate2fields_large(
        self, contentbits1, contentbits2, clocaldatapart1, clocaldatapart2
    ):
        """
        Link values from tested large community to field names in matched candidate
        """
        fields = {}
        if "format" in clocaldatapart1:
            if clocaldatapart1["format"] == "binary":
                contentbits1 = self._decimal2bits(contentbits1, 32)
        if "format" in clocaldatapart2:
            if clocaldatapart2["format"] == "binary":
                contentbits2 = self._decimal2bits(contentbits2, 32)

        pos = 0
        foffset = 0
        for fid, field in enumerate(clocaldatapart1["fields"]):
            if "length" in field:
                length = field["length"]
            else:
                length = len(contentbits1)
            fields[foffset + fid] = contentbits1[pos: pos + length]
            pos = pos + length

        pos = 0
        foffset = len(clocaldatapart1["fields"])
        for fid, field in enumerate(clocaldatapart2["fields"]):
            if "length" in field:
                length = field["length"]
            else:
                length = len(contentbits2)
            fields[foffset + fid] = contentbits2[pos: pos + length]
            pos = pos + length
        return fields

    def _decimal2bits(self, decimal, length):
        """
        Convert decimal value to bit string
        """
        return f"{int(decimal):0{length}b}"

    def _print_match(self, community, candidate, fieldvals):
        """
        Return out a matched community description
        """
        output_sections = []
        output_fields = []
        for attr in ("globaladmin", "asn", "asn4"):
            if attr in candidate:
                asn = candidate[attr]
        if "localadmin" in candidate:
            for fid, field in enumerate(candidate["localadmin"]["fields"]):
                if "description" in field:
                    output_fields.append(f'{field["name"]}={field["description"]}')
                else:
                    output_fields.append(f'{field["name"]}={fieldvals[fid]}')
            output_sections.append(",".join(output_fields))
        elif "localdatapart1" in candidate:
            offset = 0
            output_fields = []
            for fid, field in enumerate(candidate["localdatapart1"]["fields"]):
                if "description" in field:
                    output_fields.append(f"{field['name']}={field['description']}")
                else:
                    output_fields.append(f"{field['name']}={fieldvals[offset + fid]}")
            output_sections.append(",".join(output_fields))

            offset = len(candidate["localdatapart1"]["fields"])
            output_fields = []
            for fid, field in enumerate(candidate["localdatapart2"]["fields"]):
                if "description" in field:
                    output_fields.append(f'{field["name"]}={field["description"]}')
                else:
                    output_fields.append(f'{field["name"]}={fieldvals[offset + fid]}')
            output_sections.append(",".join(output_fields))

        return f"{asn}:{':'.join(output_sections)}"
