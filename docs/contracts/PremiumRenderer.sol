// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract PremiumRenderer {

    uint256 internal constant RUN_MIN = 9;

    struct Pat {
        uint8   tDigit;
        uint8   lDigit;
        uint256 trail;
        uint256 lead;
        uint8   digit;
        uint256 streak;
        uint256 total;
        bool    leadingWin;
        bool    valid;
    }

    struct Theme {
        string bg0;
        string bg1;
        string accent;
        string dim;
        string panel;
        string tier;
        string mark;
    }

    function tokenURI(uint256 tokenId, address wallet)
        external pure returns (string memory)
    {
        Pat memory p = _analyze(wallet);

        string memory image = string(abi.encodePacked(
            "data:image/svg+xml;base64,", Base64.encode(bytes(_svg(wallet, p)))
        ));

        string memory json = string(abi.encodePacked(
            '{"name":"Premium Address #', _u(tokenId),
            '","description":"On-chain hacker-style vanity address NFT rendered as a terminal dossier. Every trait line is derived from the address; the run of identical leading/trailing digits glows. Rarity (colors) scales with the run length.",',
            '"attributes":[', _attributes(p),
            '],"image":"', image, '"}'
        ));

        return string(abi.encodePacked(
            "data:application/json;base64,", Base64.encode(bytes(json))
        ));
    }

    function renderSVG(address wallet) external pure returns (string memory) {
        return _svg(wallet, _analyze(wallet));
    }

    function traitsOf(address wallet) external pure returns (
        string memory pattern,
        uint8 digit,
        uint256 streak,
        uint256 leading,
        uint256 trailing,
        uint256 occurrences,
        string memory tier,
        uint256 rarityScore
    ) {
        Pat memory p = _analyze(wallet);
        pattern = _patternStr(p);
        digit = p.digit;
        streak = p.streak;
        leading = p.lead;
        trailing = p.trail;
        occurrences = p.total;
        tier = _tierName(p.streak);
        rarityScore = _rarityScore(p);
    }

    function _nibble(address a, uint256 i) internal pure returns (uint8) {
        return uint8((uint160(a) >> ((39 - i) * 4)) & 0xf);
    }

    function _analyze(address a) internal pure returns (Pat memory p) {
        p.tDigit = _nibble(a, 39);
        for (uint256 i = 0; i < 40; i++) {
            if (_nibble(a, 39 - i) == p.tDigit) p.trail++; else break;
        }
        p.lDigit = _nibble(a, 0);
        for (uint256 i = 0; i < 40; i++) {
            if (_nibble(a, i) == p.lDigit) p.lead++; else break;
        }

        bool tOk = p.tDigit <= 9 && p.trail >= RUN_MIN;
        bool lOk = p.lDigit <= 9 && p.lead >= RUN_MIN;
        p.valid = tOk || lOk;

        if (tOk && (!lOk || p.trail >= p.lead)) {
            p.digit = p.tDigit;
            p.streak = p.trail;
            p.leadingWin = false;
        } else if (lOk) {
            p.digit = p.lDigit;
            p.streak = p.lead;
            p.leadingWin = true;
        }

        if (p.valid) {
            for (uint256 i = 0; i < 40; i++) {
                if (_nibble(a, i) == p.digit) p.total++;
            }
        }
    }

    function _attributes(Pat memory p) internal pure returns (string memory) {
        return string(abi.encodePacked(
            '{"trait_type":"Pattern","value":"', _patternStr(p), '"},',
            '{"trait_type":"Digit","value":"', _digitStr(p.digit), '"},',
            '{"trait_type":"Class","value":"', _classOf(p.digit), '"},',
            '{"trait_type":"Rank","value":"', _rankOf(p.streak), '"},',
            '{"trait_type":"Tier","value":"', _tierName(p.streak), '"},',
            '{"display_type":"number","trait_type":"Streak","value":', _u(p.streak), '},',
            '{"display_type":"number","trait_type":"Leading","value":', _u(p.lead), '},',
            '{"display_type":"number","trait_type":"Trailing","value":', _u(p.trail), '},',
            '{"display_type":"number","trait_type":"Occurrences","value":', _u(p.total), '},',
            '{"display_type":"number","trait_type":"Rarity Score","value":', _u(_rarityScore(p)), '}'
        ));
    }

    function _tierName(uint256 streak) internal pure returns (string memory) {
        if (streak >= 14) return "Legendary";
        if (streak >= 12) return "Epic";
        if (streak >= 10) return "Rare";
        return "Common";
    }

    function _rarityScore(Pat memory p) internal pure returns (uint256) {
        if (!p.valid) return 0;
        return (p.streak - (RUN_MIN - 1)) * 100 + p.total * 5;
    }

    function _patternStr(Pat memory p) internal pure returns (string memory) {
        if (!p.valid) return "None";
        return p.leadingWin ? "Leading" : "Trailing";
    }

    function _classOf(uint8 d) internal pure returns (string memory) {
        if (d == 0) return "NULL";
        if (d == 1) return "GENESIS";
        if (d == 2) return "BINARY";
        if (d == 3) return "TRINITY";
        if (d == 4) return "LATTICE";
        if (d == 5) return "CIPHER";
        if (d == 6) return "DAEMON";
        if (d == 7) return "PHANTOM";
        if (d == 8) return "OCTET";
        if (d == 9) return "OMEGA";
        return "HEX";
    }

    function _rankOf(uint256 s) internal pure returns (string memory) {
        if (s >= 20) return "ABSOLUTE";
        if (s >= 18) return "SINGULARITY";
        if (s >= 16) return "OVERLORD";
        if (s >= 14) return "ARCHITECT";
        if (s >= 12) return "INFILTRATOR";
        if (s >= 10) return "OPERATOR";
        return "INITIATE";
    }

    function _theme(uint256 streak) internal pure returns (Theme memory t) {
        if (streak >= 14) {
            t = Theme("#1a0d01", "#070300", "#ffb000", "#b29a6a", "#7a5410", "LEGENDARY", unicode"\u25C6\u25C6\u25C6\u25C6");
        } else if (streak >= 12) {
            t = Theme("#160320", "#06010a", "#ff2bd1", "#9a6f93", "#7a1f63", "EPIC", unicode"\u25C6\u25C6\u25C6");
        } else if (streak >= 10) {
            t = Theme("#02141f", "#01070b", "#00e5ff", "#6f97a6", "#1f6173", "RARE", unicode"\u25C6\u25C6");
        } else {
            t = Theme("#04110b", "#020405", "#39ff14", "#6f8f78", "#1f6b3a", "COMMON", unicode"\u25C6");
        }
    }

    function _svg(address a, Pat memory p) internal pure returns (string memory) {
        Theme memory t = _theme(p.streak);
        return string(abi.encodePacked(
            '<svg viewBox="0 0 350 350" xmlns="http://www.w3.org/2000/svg" font-family="ui-monospace,Menlo,Consolas,monospace">',
            _defs(t),
            _header(t),
            _rows(t, p),
            _addr(a, p, t),
            '</svg>'
        ));
    }

    function _defs(Theme memory t) internal pure returns (string memory) {
        return string(abi.encodePacked(
            '<defs>',
            '<radialGradient id="bg" cx="50%" cy="24%" r="95%"><stop offset="0%" stop-color="', t.bg0,
                '"/><stop offset="100%" stop-color="', t.bg1, '"/></radialGradient>',
            '<filter id="glow" x="-40%" y="-40%" width="180%" height="180%"><feGaussianBlur stdDeviation="2" result="b"/>',
                '<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>',
            '<pattern id="scan" width="3" height="3" patternUnits="userSpaceOnUse"><rect width="3" height="1" fill="', t.accent, '" opacity="0.04"/></pattern>',
            '</defs>'
        ));
    }

    function _header(Theme memory t) internal pure returns (string memory) {
        return string(abi.encodePacked(
            '<rect width="350" height="350" fill="url(#bg)"/><rect width="350" height="350" fill="url(#scan)"/>',
            '<rect x="10" y="10" width="330" height="330" rx="10" fill="none" stroke="', t.panel, '" stroke-width="1.2" opacity="0.6"/>',
            '<circle cx="26" cy="28" r="3.5" fill="#ff5f56"/><circle cx="38" cy="28" r="3.5" fill="#ffbd2e"/><circle cx="50" cy="28" r="3.5" fill="#27c93f"/>',
            '<text x="322" y="32" text-anchor="end" font-size="11" letter-spacing="2" fill="', t.accent, '">', t.mark, ' ', t.tier, '</text>',
            '<line x1="10" y1="44" x2="340" y2="44" stroke="', t.panel, '" stroke-width="1" opacity="0.5"/>',
            '<text x="28" y="72" font-size="11" fill="', t.dim, '">&gt; cat /vault/identity <tspan fill="', t.accent, '">OK</tspan> _</text>'
        ));
    }

    function _rows(Theme memory t, Pat memory p) internal pure returns (string memory) {
        return string(abi.encodePacked(
            _row("CLASS",     string(abi.encodePacked(_classOf(p.digit), "-", _digitStr(p.digit))), "104", t),
            _row("RANK",      _rankOf(p.streak), "133", t),
            _row("SEQUENCE",  string(abi.encodePacked(_u(p.streak), " x [", _digitStr(p.digit), "]")), "162", t),
            _row("ANCHOR",    p.leadingWin ? "PREFIX-LOCK" : "SUFFIX-LOCK", "191", t),
            _row("ENTROPY",   string(abi.encodePacked("x", _u(p.total))), "220", t),
            _row("INTEGRITY", _u(_rarityScore(p)), "249", t)
        ));
    }

    function _row(string memory label, string memory value, string memory y, Theme memory t)
        internal pure returns (string memory)
    {
        return string(abi.encodePacked(
            '<text x="28" y="', y, '" font-size="13" letter-spacing="1" fill="', t.dim, '">', label, '</text>',
            '<text x="322" y="', y, '" text-anchor="end" font-size="14" font-weight="700" fill="', t.accent, '" filter="url(#glow)">', value, '</text>'
        ));
    }

    function _addr(address a, Pat memory p, Theme memory t) internal pure returns (string memory) {
        return string(abi.encodePacked(
            '<line x1="28" y1="296" x2="322" y2="296" stroke="', t.panel, '" stroke-width="1" opacity="0.35"/>',
            '<text x="28" y="320" font-size="12" textLength="294" lengthAdjust="spacingAndGlyphs">',
                '<tspan fill="', t.dim, '">0x</tspan>', _addrSpans(a, p, t),
            '</text>'
        ));
    }

    function _addrSpans(address a, Pat memory p, Theme memory t) internal pure returns (string memory out) {
        for (uint256 i = 0; i < 40; i++) {
            bool hi = _isHi(p, i);
            out = string(abi.encodePacked(
                out,
                '<tspan fill="', hi ? t.accent : t.dim, '"',
                hi ? ' font-weight="700" filter="url(#glow)"' : '',
                '>', _digitStr(_nibble(a, i)), '</tspan>'
            ));
        }
    }

    function _isHi(Pat memory p, uint256 i) internal pure returns (bool) {
        if (!p.valid) return false;
        if (p.leadingWin) return i < p.streak;
        return i >= 40 - p.streak;
    }

    function _digitStr(uint8 v) internal pure returns (string memory) {
        bytes memory b = new bytes(1);
        b[0] = v < 10 ? bytes1(uint8(48 + v)) : bytes1(uint8(87 + v));
        return string(b);
    }

    function _u(uint256 v) internal pure returns (string memory) {
        if (v == 0) return "0";
        uint256 j = v;
        uint256 len;
        while (j != 0) { len++; j /= 10; }
        bytes memory b = new bytes(len);
        while (v != 0) { len--; b[len] = bytes1(uint8(48 + v % 10)); v /= 10; }
        return string(b);
    }
}

library Base64 {
    bytes internal constant _TABLE =
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

    function encode(bytes memory data) internal pure returns (string memory) {
        if (data.length == 0) return "";
        bytes memory table = _TABLE;
        uint256 encodedLen = 4 * ((data.length + 2) / 3);
        string memory result = new string(encodedLen + 32);

        assembly {
            let tablePtr := add(table, 1)
            let resultPtr := add(result, 32)
            for { let i := 0 } lt(i, mload(data)) {} {
                i := add(i, 3)
                let input := and(mload(add(data, i)), 0xffffff)
                let out := mload(add(tablePtr, and(shr(18, input), 0x3F)))
                out := shl(8, out)
                out := add(out, and(mload(add(tablePtr, and(shr(12, input), 0x3F))), 0xFF))
                out := shl(8, out)
                out := add(out, and(mload(add(tablePtr, and(shr(6, input), 0x3F))), 0xFF))
                out := shl(8, out)
                out := add(out, and(mload(add(tablePtr, and(input, 0x3F))), 0xFF))
                out := shl(224, out)
                mstore(resultPtr, out)
                resultPtr := add(resultPtr, 4)
            }
            switch mod(mload(data), 3)
            case 1 { mstore(sub(resultPtr, 2), shl(240, 0x3d3d)) }
            case 2 { mstore(sub(resultPtr, 1), shl(248, 0x3d)) }
            mstore(result, encodedLen)
        }
        return result;
    }
}
